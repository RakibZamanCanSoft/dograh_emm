"""API routes for Prompt Refactor Model configuration.

Stores an OpenAI-compatible API key (org-scoped) that is used exclusively
for rewriting Agent Builder-generated prompts to be channel-aware.

Security model: same as BYOK model configuration.
- Key is stored plain-text in the DB (needed at runtime — same as all other keys).
- GET always returns the key masked (last 4 chars visible).
- PUT: if the incoming key matches the stored mask, the real stored key is kept
  (i.e. the user just clicked Save without changing anything).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel

from api.db import db_client

from api.routes.auth import get_user
from api.routes.auth import UserModel
from api.services.configuration.masking import contains_masked_key, is_mask_of, mask_key

router = APIRouter(prefix="/prompt-refactor-config", tags=["prompt-refactor-config"])

# Key used in the OrganizationConfiguration table
_CONFIG_KEY = "prompt_refactor_openai_api_key"


class PromptRefactorConfigResponse(BaseModel):
    api_key: Optional[str] = None  # always masked when returned
    is_configured: bool = False


class PromptRefactorConfigRequest(BaseModel):
    api_key: str


@router.get("", response_model=PromptRefactorConfigResponse)
async def get_prompt_refactor_config(
    user: UserModel = Depends(get_user),
) -> PromptRefactorConfigResponse:
    """Return the current prompt refactor model config (key is masked)."""
    org_id = user.selected_organization_id
    real_key: Optional[str] = await db_client.get_configuration_value(
        organization_id=org_id, key=_CONFIG_KEY
    )
    if not real_key:
        return PromptRefactorConfigResponse(api_key=None, is_configured=False)

    return PromptRefactorConfigResponse(
        api_key=mask_key(real_key),
        is_configured=True,
    )


@router.put("", response_model=PromptRefactorConfigResponse)
async def save_prompt_refactor_config(
    request: PromptRefactorConfigRequest,
    user: UserModel = Depends(get_user),
) -> PromptRefactorConfigResponse:
    """Save or update the prompt refactor OpenAI API key.

    If the submitted key is masked (user did not change it), the existing
    real key is preserved. A blank key clears the configuration.
    """
    org_id = user.selected_organization_id
    incoming_key = request.api_key.strip()

    # Blank → delete config
    if not incoming_key:
        await db_client.delete_configuration(organization_id=org_id, key=_CONFIG_KEY)
        logger.info(f"[prompt_refactor_config] Cleared config for org {org_id}")
        return PromptRefactorConfigResponse(api_key=None, is_configured=False)

    # If masked → keep real stored key (user didn't actually change it)
    if contains_masked_key(incoming_key):
        existing: Optional[str] = await db_client.get_configuration_value(
            organization_id=org_id, key=_CONFIG_KEY
        )
        if existing and is_mask_of(incoming_key, existing):
            logger.debug(
                f"[prompt_refactor_config] Incoming key is masked placeholder for org {org_id}; keeping real key."
            )
            return PromptRefactorConfigResponse(
                api_key=mask_key(existing),
                is_configured=True,
            )
        # Mask didn't match stored key — treat as new key anyway (shouldn't normally happen)

    # Persist real key
    await db_client.upsert_configuration(
        organization_id=org_id, key=_CONFIG_KEY, value=incoming_key
    )
    logger.info(f"[prompt_refactor_config] Saved new key for org {org_id}")
    return PromptRefactorConfigResponse(
        api_key=mask_key(incoming_key),
        is_configured=True,
    )


@router.delete("", response_model=PromptRefactorConfigResponse)
async def delete_prompt_refactor_config(
    user: UserModel = Depends(get_user),
) -> PromptRefactorConfigResponse:
    """Remove the stored prompt refactor API key."""
    org_id = user.selected_organization_id
    await db_client.delete_configuration(organization_id=org_id, key=_CONFIG_KEY)
    logger.info(f"[prompt_refactor_config] Deleted config for org {org_id}")
    return PromptRefactorConfigResponse(api_key=None, is_configured=False)


# ---------------------------------------------------------------------------
# Helper used by prompt_refactor.py to read the real key at runtime
# ---------------------------------------------------------------------------

async def get_prompt_refactor_api_key(organization_id: int) -> Optional[str]:
    """Return the real (unmasked) stored API key for an org, or None."""
    return await db_client.get_configuration_value(
        organization_id=organization_id, key=_CONFIG_KEY
    )
