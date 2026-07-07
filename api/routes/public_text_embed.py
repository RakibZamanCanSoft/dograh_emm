from datetime import UTC, datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from loguru import logger
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import WorkflowRunTextSessionModel
from api.enums import WorkflowRunMode
from api.routes.public_embed import (
    InitEmbedRequest,
    _allow_embed_origin,
    generate_session_token,
    get_request_origin,
    validate_origin,
)
from api.routes.workflow_text_chat import (
    AppendTextChatMessageRequest,
    WorkflowRunTextSessionResponse,
    _build_response,
    _execute_pending_turn_response,
    _revision_conflict_detail,
)
from api.services.workflow.text_chat_session_service import (
    TextChatSessionRevisionConflictError,
    append_text_chat_user_message,
    default_text_chat_checkpoint,
    default_text_chat_session_data,
    initialize_text_chat_session,
)
from pipecat.utils.run_context import set_current_run_id

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
    if not validate_origin(origin, embed_token.allowed_domains or []):
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
    if embed_token.usage_limit and embed_token.usage_count >= embed_token.usage_limit:
        raise HTTPException(status_code=403, detail="Embed token usage limit exceeded")

    if not validate_origin(origin, embed_token.allowed_domains or []):
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {origin}")

    if origin:
        _allow_embed_origin(response, origin)

    session_name = f"WR-TEXT-EMBED-{uuid4().hex[:6].upper()}"
    try:
        workflow_run = await db_client.create_workflow_run(
            name=session_name,
            workflow_id=embed_token.workflow_id,
            mode=WorkflowRunMode.TEXTCHAT.value,
            user_id=embed_token.created_by,
            initial_context={
                **(init_request.context_variables or {}),
                "provider": WorkflowRunMode.TEXTCHAT.value,
            },
            use_draft=False, # Use published workflow for embeds
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    set_current_run_id(workflow_run.id)

    from api.services.quota_service import authorize_workflow_run_start
    quota_result = await authorize_workflow_run_start(
        workflow_id=embed_token.workflow_id,
        workflow_run_id=workflow_run.id,
        actor_user=None,
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
    # Expire text chats after 24h
    from datetime import timedelta
    await db_client.create_embed_session(
        session_token=session_token,
        embed_token_id=embed_token.id,
        workflow_run_id=workflow_run.id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
        origin=origin[:255],
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    await db_client.increment_embed_token_usage(embed_token.id)

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
    text_session, workflow_id = await _load_public_text_session_or_404(session_token, origin)
    
    if origin:
        _allow_embed_origin(res, origin)

    if text_session.workflow_run and text_session.workflow_run.is_completed:
        raise HTTPException(status_code=400, detail="Text chat session is already completed")

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
    text_session, workflow_id = await _load_public_text_session_or_404(session_token, origin)
    
    if origin:
        _allow_embed_origin(res, origin)

    return _build_response(text_session)


@router.options("/init")
async def options_init(request: Request):
    from api.routes.public_embed import _cors_response
    origin = request.headers.get("origin", "*")
    return _cors_response(origin, "POST, OPTIONS")


@router.options("/{session_token}/messages")
async def options_text_messages(request: Request):
    from api.routes.public_embed import _cors_response
    origin = request.headers.get("origin", "*")
    return _cors_response(origin, "POST, OPTIONS")


@router.options("/{session_token}")
async def options_text_session(request: Request):
    from api.routes.public_embed import _cors_response
    origin = request.headers.get("origin", "*")
    return _cors_response(origin, "GET, OPTIONS")
