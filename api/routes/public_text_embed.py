from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pipecat.utils.run_context import set_current_run_id
from pydantic import BaseModel

from api.db import db_client
from api.db.models import WorkflowRunTextSessionModel
from api.enums import CallType, WorkflowRunMode
from api.routes.public_embed import (
    InitEmbedRequest,
    _allow_embed_origin,
    _cors_response,
    generate_session_token,
    get_request_origin,
)
from api.routes.workflow_text_chat import (
    AppendTextChatMessageRequest,
    WorkflowRunTextSessionResponse,
    _build_response,
    _execute_pending_turn_response,
    _revision_conflict_detail,
)
from api.services.workflow.embed_context import sanitize_embed_context_variables
from api.services.workflow.embed_session_service import (
    authorize_embed_workflow_run_start,
    validate_embed_origin,
)
from api.services.workflow.run_creation import prepare_workflow_run_inputs
from api.services.workflow.text_chat_session_service import (
    TextChatSessionRevisionConflictError,
    append_text_chat_user_message,
    default_text_chat_checkpoint,
    default_text_chat_session_data,
    initialize_text_chat_session,
)

router = APIRouter(prefix="/public/text-embed", tags=["public-text-embed"])


class InitTextEmbedResponse(BaseModel):
    session_token: str
    workflow_run_id: int
    text_session: WorkflowRunTextSessionResponse
    config: dict


async def _load_public_text_session_or_404(
    session_token: str, origin: str
) -> tuple[WorkflowRunTextSessionModel, int]:
    # Validate session token
    embed_session = await db_client.get_embed_session_by_token(session_token)
    if not embed_session:
        raise HTTPException(status_code=404, detail="Invalid session token")

    # Check expiration
    if embed_session.expires_at and embed_session.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=403, detail="Session expired")

    # Validate domain
    embed_token = await db_client.get_embed_token_by_id(embed_session.embed_token_id)
    if not embed_token:
        raise HTTPException(status_code=404, detail="Invalid embed token")
    if not validate_embed_origin(origin, embed_token.allowed_domains or []):
        raise HTTPException(status_code=403, detail="Domain not allowed")

    # Load text session
    run_id = embed_session.workflow_run_id
    set_current_run_id(run_id)
    text_session = await db_client.get_workflow_run_text_session(
        run_id, organization_id=embed_token.organization_id
    )
    if not text_session or not text_session.workflow_run:
        raise HTTPException(status_code=404, detail="Text chat session not found")
    if text_session.workflow_run.mode != WorkflowRunMode.TEXTCHAT.value:
        raise HTTPException(
            status_code=400, detail="Workflow run is not a text chat session"
        )
    return text_session, embed_token.workflow_id


@router.post("/init", response_model=InitTextEmbedResponse)
async def initialize_text_embed_session(
    request: Request, init_request: InitEmbedRequest, response: Response
):
    origin = get_request_origin(request)

    # Validate embed token
    embed_token = await db_client.get_embed_token_by_token(init_request.token)
    if not embed_token:
        raise HTTPException(status_code=404, detail="Invalid embed token")
    if not embed_token.is_active:
        raise HTTPException(status_code=403, detail="Embed token is inactive")
    if embed_token.expires_at and embed_token.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=403, detail="Embed token has expired")

    if not validate_embed_origin(origin, embed_token.allowed_domains or []):
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {origin}")

    if origin:
        _allow_embed_origin(response, origin)

    usage_reserved = await db_client.reserve_embed_token_usage(
        embed_token.id, embed_token.organization_id
    )
    if not usage_reserved:
        raise HTTPException(status_code=403, detail="Embed token usage limit exceeded")

    session_name = f"WR-TEXT-EMBED-{uuid4().hex[:6].upper()}"
    try:
        workflow = await db_client.get_workflow(
            embed_token.workflow_id, organization_id=embed_token.organization_id
        )
        if not workflow:
            raise ValueError("Workflow not found")
        run_inputs = await prepare_workflow_run_inputs(db_client, workflow)
        context_variables = sanitize_embed_context_variables(
            init_request.context_variables
        )
        workflow_run = await db_client.create_workflow_run(
            name=session_name,
            workflow_id=embed_token.workflow_id,
            mode=WorkflowRunMode.TEXTCHAT.value,
            user_id=embed_token.created_by,
            organization_id=embed_token.organization_id,
            call_type=CallType.INBOUND,
            initial_context={
                **context_variables,
                "provider": WorkflowRunMode.TEXTCHAT.value,
            },
            definition_id=run_inputs.definition_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    set_current_run_id(workflow_run.id)

    quota_result = await authorize_embed_workflow_run_start(
        embed_token=embed_token,
        workflow_run_id=workflow_run.id,
    )
    if not quota_result.has_quota:
        raise HTTPException(status_code=402, detail=quota_result.error_message)

    annotations = {
        "tester": {
            "source": "web_embed",
            "modality": "text",
        }
    }
    workflow_run = await db_client.update_workflow_run(
        workflow_run.id,
        annotations=annotations,
    )

    text_session = await db_client.ensure_workflow_run_text_session(
        workflow_run.id,
        session_data=default_text_chat_session_data(),
        checkpoint=default_text_chat_checkpoint(),
    )

    try:
        text_session = await initialize_text_chat_session(
            run_id=workflow_run.id,
            text_session=text_session,
        )
    except TextChatSessionRevisionConflictError as e:
        raise HTTPException(status_code=409, detail=_revision_conflict_detail(e))

    initial_text_response = await _execute_pending_turn_response(
        workflow_id=embed_token.workflow_id,
        run_id=workflow_run.id,
        text_session=text_session,
    )

    session_token = generate_session_token()
    await db_client.create_embed_session(
        session_token=session_token,
        embed_token_id=embed_token.id,
        workflow_run_id=workflow_run.id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
        origin=origin[:255],
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )

    config = {
        "workflow_id": embed_token.workflow_id,
        "workflow_run_id": workflow_run.id,
        **(embed_token.settings or {}),
    }

    return InitTextEmbedResponse(
        session_token=session_token,
        workflow_run_id=workflow_run.id,
        text_session=initial_text_response,
        config=config,
    )


@router.post(
    "/{session_token}/messages",
    response_model=WorkflowRunTextSessionResponse,
)
async def append_public_text_chat_message(
    session_token: str,
    request: AppendTextChatMessageRequest,
    req: Request,
    res: Response,
):
    origin = get_request_origin(req)
    text_session, workflow_id = await _load_public_text_session_or_404(
        session_token, origin
    )

    if origin:
        _allow_embed_origin(res, origin)

    if text_session.workflow_run and text_session.workflow_run.is_completed:
        raise HTTPException(
            status_code=400, detail="Text chat session is already completed"
        )

    try:
        text_session = await append_text_chat_user_message(
            run_id=text_session.workflow_run_id,
            text_session=text_session,
            user_text=request.text,
            expected_revision=request.expected_revision,
        )
    except TextChatSessionRevisionConflictError as e:
        raise HTTPException(status_code=409, detail=_revision_conflict_detail(e))

    return await _execute_pending_turn_response(
        workflow_id=workflow_id,
        run_id=text_session.workflow_run_id,
        text_session=text_session,
    )


@router.get(
    "/{session_token}",
    response_model=WorkflowRunTextSessionResponse,
)
async def get_public_text_chat_session(
    session_token: str,
    req: Request,
    res: Response,
):
    origin = get_request_origin(req)
    text_session, _ = await _load_public_text_session_or_404(session_token, origin)

    if origin:
        _allow_embed_origin(res, origin)

    return _build_response(text_session)


@router.options("/init")
async def options_init(request: Request):
    origin = request.headers.get("origin", "*")
    return _cors_response(origin, "POST, OPTIONS")


@router.options("/{session_token}/messages")
async def options_text_messages(request: Request):
    origin = request.headers.get("origin", "*")
    return _cors_response(origin, "POST, OPTIONS")


@router.options("/{session_token}")
async def options_text_get(request: Request):
    origin = request.headers.get("origin", "*")
    return _cors_response(origin, "GET, OPTIONS")
