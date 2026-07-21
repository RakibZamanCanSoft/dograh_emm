"""LLM-powered prompt refactoring for Agent Builder generated workflows.

When a user creates a Chat Agent or Call+Chat Agent via the Agent Builder,
the MPS backend always generates voice-call-biased prompts.  This module
sends every node's prompt through an LLM to intelligently rewrite it for
the chosen channel.

Priority order for the LLM used:
  1. The user's own configured LLM (Dograh managed, BYOK, or local model).
     This is the preferred path — no extra config needed.
  2. A standalone AGENT_BUILDER_LLM_API_KEY env var as a fallback, pointing
     at any OpenAI-compatible endpoint (useful for dev environments without
     a model configured).

Using the user's configured LLM means:
- Dograh users: MPS LLM endpoint is used automatically via their Dograh key.
- BYOK users (OpenAI, Groq, OpenRouter, local models, etc.): their own key
  and endpoint are used.  Adding an OpenAI key in BYOK does NOT affect
  agent runs — the prompt refactoring call is a one-shot background call
  at workflow creation time only.
- Future local-model users: as long as the endpoint is OpenAI-compatible
  (Ollama, vLLM, Speaches, etc.) it will work transparently.

Providers that do NOT speak the OpenAI chat-completions protocol (AWS Bedrock,
Google Vertex, Realtime models, Azure Speech, etc.) are skipped gracefully —
the original prompts are returned unchanged in those cases.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import httpx
from loguru import logger

from api.constants import MPS_API_URL
from api.services.configuration.registry import ServiceProviders

if TYPE_CHECKING:
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration

# ---------------------------------------------------------------------------
# Fallback env-var config (used when no user LLM is configured)
# ---------------------------------------------------------------------------

_FALLBACK_API_KEY: Optional[str] = (
    os.getenv("AGENT_BUILDER_LLM_API_KEY")
    or os.getenv("OPENAI_API_KEY")
)
_FALLBACK_BASE_URL: str = os.getenv(
    "AGENT_BUILDER_LLM_BASE_URL", "https://api.openai.com/v1"
).rstrip("/")
_FALLBACK_MODEL: str = os.getenv("AGENT_BUILDER_LLM_MODEL", "gpt-4.1-mini")

# ---------------------------------------------------------------------------
# Resolved LLM connection details
# ---------------------------------------------------------------------------

@dataclass
class _LLMEndpoint:
    base_url: str
    api_key: str
    model: str


def _resolve_endpoint(
    ai_model_config: Optional["EffectiveAIModelConfiguration"],
) -> Optional[_LLMEndpoint]:
    """Try to extract an OpenAI-compatible chat-completions endpoint from
    the user's configured LLM.

    Returns None if the provider is not OpenAI-compatible (e.g. Bedrock,
    Google Vertex, realtime-only models) so the caller can fall back.
    """
    # ── OpenAI-compatible providers that have a chat-completions endpoint ──
    _COMPATIBLE_PROVIDERS = {
        ServiceProviders.OPENAI,
        ServiceProviders.GROQ,
        ServiceProviders.OPENROUTER,
        ServiceProviders.SPEACHES,   # local / Ollama / vLLM
        ServiceProviders.HUGGINGFACE,
        ServiceProviders.MINIMAX,
        ServiceProviders.SARVAM,
        ServiceProviders.INWORLD,
    }

    llm = getattr(ai_model_config, "llm", None) if ai_model_config else None

    # ── Dograh managed LLM ────────────────────────────────────────────────
    if llm is not None and getattr(llm, "provider", None) in (
        ServiceProviders.DOGRAH,
        ServiceProviders.DOGRAH.value,
    ):
        api_key = llm.api_key  # random-selected if list
        if not api_key:
            return None
        # MPS exposes an OpenAI-compatible endpoint at /api/v1/llm
        return _LLMEndpoint(
            base_url=f"{MPS_API_URL}/api/v1/llm",
            api_key=api_key,
            model=getattr(llm, "model", "default") or "default",
        )

    # ── OpenAI-compatible BYOK / local providers ──────────────────────────
    if llm is not None and getattr(llm, "provider", None) in _COMPATIBLE_PROVIDERS:
        api_key = llm.api_key  # may be None for no-auth local endpoints
        base_url = getattr(llm, "base_url", None)
        model = getattr(llm, "model", None)
        if not base_url or not model:
            return None
        return _LLMEndpoint(
            base_url=base_url.rstrip("/"),
            api_key=api_key or "none",  # placeholder for endpoints without auth
            model=model,
        )

    # ── Unsupported / realtime-only provider ─────────────────────────────
    return None


def refactor_end_node_chat_prompt(prompt: str) -> str:
    """Adapt an end node system prompt from voice call to text chat.

    Replaces call-specific phrases with chat equivalents while keeping
    100% of the system prompt layout and instructions intact.
    """
    if not prompt:
        return prompt

    res = prompt
    replacements = [
        ("end the call", "end the chat"),
        ("End the call", "End the chat"),
        ("end call", "end chat"),
        ("End call", "End chat"),
        ("End Call", "End Chat"),
        ("The call is over.", "The chat is over."),
        ("the call is over.", "the chat is over."),
        ("Thank you for the call.", "Thank you for chatting."),
        ("Thank you for the call", "Thank you for chatting"),
        ("for the call", "for chatting"),
        ("on the call", "in the chat"),
        ("during the call", "during the chat"),
    ]
    for old, new in replacements:
        res = res.replace(old, new)
    return res


# ---------------------------------------------------------------------------
# System prompts per agent_type
# ---------------------------------------------------------------------------

_SYSTEM_CHAT_ONLY = """\
You are an expert AI assistant that rewrites agent workflow prompts.

The input prompt was auto-generated for a VOICE CALL AI agent.
Your job is to rewrite it so it works perfectly for a TEXT CHAT agent only.

CRITICAL FORMATTING & STRUCTURE RULES:
1. THIS IS A SYSTEM PROMPT FOR AN LLM AGENT, NOT A CONVERSATIONAL SCRIPT OR DIALOGUE TRANSCRIPT.
2. DO NOT write out simulated dialogue, turn-by-turn scripts, or stage directions.
3. YOU MUST PRESERVE THE EXACT STRUCTURE, HEADERS, MARKDOWN FORMATTING, HTML/XML TAGS (such as <FORMAT>, </FORMAT>), SECTIONS (such as # MAIN ACTION POINT AT THIS STEP:, ## Usable details and Main Agenda, ## USABLE DETAILS and GOALS AT THIS STAGE:, [[ Relevant Questions: ]], [[ Brief Wrap Up Details: ]], ## Flow of chat, ## Constraints), AND BULLET POINTS OF THE ORIGINAL PROMPT.
4. Keep the core logic and structure intact, only updating channel-specific language from voice to chat and adding the chat data-collection rules.

Rules:
- Replace ALL voice-call-specific language with text-chat equivalents.
  Examples: "call" → "chat", "caller" → "user", "speak"/"say" → "write"/"type",
  "Voice AI Agent" → "Chat Assistant", "phone call" → "chat session",
  "inbound call" → "chat request", "end the call" → "end the chat",
  "you have received an inbound call" → "a user has started a chat with you",
  "Flow of call" → "Flow of chat", "Move to End Call" → "Move to End Chat".
- Remove or replace the entire ASR/transcription noise handling section.
  Replace it with: "The user is communicating via text. Read their messages exactly."
- Remove instructions to ask users to spell names letter-by-letter or say
  phone numbers digit-by-digit. Instead, tell the agent to ask the user to
  simply type the information.
- **Repeat back**: After the user provides any piece of information (name,
  phone, email, address, date, etc.), add an instruction for the agent to
  immediately confirm it in the same message before moving on
  (e.g. "Got it, your email is [email]. Is that correct?").
- **One question at a time**: Add an explicit instruction that the agent MUST
  ask for only ONE piece of information per message. Wait for the user's reply
  before asking the next question.
  Exception: first name and last name may be asked together as a single
  combined question since they form one logical unit.
- Output ONLY the rewritten system prompt text. No explanation, no preamble.
"""

_SYSTEM_CALL_AND_CHAT = """\
You are an expert AI assistant that rewrites agent workflow prompts.

The input prompt was auto-generated for a VOICE CALL AI agent only.
Your job is to rewrite it so it works correctly for BOTH voice calls AND
text chat, depending on which channel the user is on.

The channel is available at runtime as the template variable {{provider}}.
- When {{provider}} == "textchat"  → the user is typing via a website chat widget.
- When {{provider}} != "textchat"  → the user is on a live voice call.

CRITICAL FORMATTING & STRUCTURE RULES:
1. THIS IS A SYSTEM PROMPT FOR AN LLM AGENT, NOT A CONVERSATIONAL SCRIPT OR DIALOGUE TRANSCRIPT.
2. DO NOT write out simulated dialogue, turn-by-turn scripts, or stage directions.
3. YOU MUST PRESERVE THE EXACT STRUCTURE, HEADERS, MARKDOWN FORMATTING, HTML/XML TAGS, SECTIONS, AND BULLET POINTS OF THE ORIGINAL PROMPT.

Rules:
- Replace hardcoded voice-only phrasing with channel-aware equivalents.
  Use conditional language such as: "if on a call, do X; if in a chat, do Y."
  Or use neutral language that works for both: e.g., "interaction" instead of
  "call", "user" instead of "caller".
- Replace "Voice AI Agent" with "AI Assistant".
- Replace the entire ASR/transcription noise handling section with this block
  (copy it verbatim, do not paraphrase):

## CHANNEL-AWARE BEHAVIOUR
The channel is determined by {{provider}}.
- If {{provider}} is NOT "textchat" (voice call): audio can be noisy. Ask for
  clarification casually ("sorry, did not catch that"). Never mention ASR or
  transcription. Ask users to spell names and say phone numbers digit by digit.
- If {{provider}} IS "textchat" (text chat): the user is typing. Read their
  exact words. Do NOT ask them to spell names or repeat digit by digit.

- Adapt the greeting/opening so it works for both voice and chat.
- Keep the STRUCTURE and LOGIC intact (flow, agenda, wrap-up, tool call rules).
- Preserve markdown formatting, headers, and lists exactly.
- Do NOT add, remove, or reorder functional steps.
- Output ONLY the rewritten system prompt text. No explanation, no preamble.
"""

_SYSTEM_PROMPTS: dict[str, str] = {
    "chat": _SYSTEM_CHAT_ONLY,
    "call_and_chat": _SYSTEM_CALL_AND_CHAT,
}

# System prompt used specifically when generating `prompt_chat` for an agentNode
# inside a call_and_chat workflow.  Here we only need a chat-only version — the
# original call-optimised prompt is preserved unchanged as `prompt`.
_SYSTEM_AGENT_NODE_CHAT_ONLY = """\
You are an expert AI assistant that rewrites a single workflow node prompt.

The input is a node prompt from a VOICE CALL AI workflow step.
Your task is to rewrite ONLY this node prompt so it works perfectly for a
TEXT CHAT session (the user is typing, not speaking).

CRITICAL FORMATTING & STRUCTURE RULES:
1. THIS IS A SYSTEM PROMPT FOR AN LLM AGENT, NOT A CONVERSATIONAL SCRIPT OR DIALOGUE TRANSCRIPT.
2. DO NOT write out simulated dialogue, turn-by-turn scripts, or stage directions.
3. YOU MUST PRESERVE THE EXACT STRUCTURE, HEADERS, MARKDOWN FORMATTING, HTML/XML TAGS (such as <FORMAT>, </FORMAT>), SECTIONS (such as # MAIN ACTION POINT AT THIS STEP:, ## Usable details and Main Agenda, ## USABLE DETAILS and GOALS AT THIS STAGE:, [[ Relevant Questions: ]], [[ Brief Wrap Up Details: ]], ## Flow of chat, ## Constraints), AND BULLET POINTS OF THE ORIGINAL PROMPT.
4. Keep the core logic and structure intact, only updating channel-specific language from voice to chat and adding the chat data-collection rules.

Rules:
- Replace ALL voice-call-specific language with text-chat equivalents.
  Examples: "call" → "chat", "caller" → "user", "speak"/"say" → "write"/"type",
  "Voice AI" → "Chat AI", "phone call" → "chat session", "Flow of call" → "Flow of chat",
  "Move to End Call" → "Move to End Chat".
- Remove ASR/transcription noise handling instructions.
  Replace with: "The user is communicating via text. Read their messages exactly."
- Remove instructions to ask users to spell names letter-by-letter or repeat
  phone numbers digit-by-digit. Instead, ask the user to simply type the info.
- **One question at a time**: Add an instruction that the agent MUST ask for
  only ONE piece of information per message. It must wait for the user's reply
  before asking the next question. Exception: first name and last name may be
  asked together as a single combined question.
- **Repeat back**: After the user provides any piece of information (name,
  phone, email, address, date, etc.), add an instruction for the agent to
  immediately repeat it back in the same message to confirm accuracy before
  moving on (e.g. "Got it, your email is [email]. Is that correct?").
- Output ONLY the rewritten system prompt text. No explanation, no preamble.
"""


# System prompt for refining call-only prompts. Applied to ALL agent types
# that include a voice-call side (call, call_and_chat).
_SYSTEM_CALL_REFACTOR = """\
You are a voice AI prompt specialist. Your task is to perform MINIMAL, SURGICAL edits on an existing voice call SYSTEM PROMPT to enhance data-collection quality.

CRITICAL FORMATTING & STRUCTURE RULES:
1. THIS IS A SYSTEM PROMPT FOR AN LLM AGENT, NOT A CONVERSATIONAL SCRIPT OR DIALOGUE TRANSCRIPT.
2. DO NOT write out simulated dialogue, turn-by-turn scripts, or stage directions (e.g. NEVER output lines like "[After the caller replies:]", "Caller:", "Agent:", or simulated dialogue turns).
3. YOU MUST PRESERVE THE EXACT STRUCTURE, HEADERS, MARKDOWN FORMATTING, HTML/XML TAGS (such as <FORMAT>, </FORMAT>), SECTIONS (such as # MAIN ACTION POINT AT THIS STEP:, ## Usable details and Main Agenda, ## USABLE DETAILS and GOALS AT THIS STAGE:, [[ Relevant Questions: ]], [[ Brief Wrap Up Details: ]], ## Flow of call, ## Constraints), AND BULLET POINTS OF THE ORIGINAL PROMPT.
4. Keep 95% of the original prompt text EXACTLY as written. Only make small, surgical inline additions to enforce data-collection quality rules.

DATA-COLLECTION ENHANCEMENT RULES (apply inline within existing sections/bullets/questions):

1. **Spelling for names and email addresses**:
   Whenever a step, objective, or question asks for a name (first name, last name, child's name, company name, caller's name, etc.) or an email address:
   - Add inline instruction to ask the caller to spell it out letter-by-letter.
   - Add inline instruction to repeat the spelling back to confirm.
   Example inline addition in goals: "Ask them spelling of the first and last name. Reconfirm the name by repeating the spelling."
   Example inline addition in relevant questions: "May I have your first and last name, please? Please spell it so that I get it correctly."

2. **Digit-by-digit for phone numbers**:
   Whenever a step, objective, or question asks for a phone number:
   - Add inline instruction to ask the caller to provide it digit by digit.
   - Add inline instruction to repeat the phone number back to confirm.
   Example inline addition in relevant questions: "Could you provide your phone number? Please tell it digit by digit so that I get it clearly."

3. **Repeat-back confirmation for all data**:
   Ensure that for EVERY piece of data collected (name, phone, email, date, time, age, address, issue, etc.), the prompt explicitly instructs the agent to repeat the value back to the caller to reconfirm before moving on.
   Example inline addition in wrap up: "Confirm the collected information: repeat the caller's name, contact details, child's name and age, the issue described, and the preferred appointment date and time."

4. **One question at a time**:
   In the Flow of call or Constraints section, ensure there is an explicit rule:
   "Ask focused questions one by one. Ask for only ONE piece of information per turn. Wait for the caller's reply before asking the next question. Exception: first name and last name may be asked together as a single combined question."

Output ONLY the surgically updated system prompt text. Do NOT add preamble, commentary, or conversational scripts.
"""


# ---------------------------------------------------------------------------
# Core refactoring logic
# ---------------------------------------------------------------------------

async def _call_chat_completions(
    endpoint: _LLMEndpoint,
    system_prompt: str,
    user_message: str,
) -> Optional[str]:
    """Make a single OpenAI chat/completions call and return the assistant text."""
    url = f"{endpoint.base_url}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {endpoint.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": endpoint.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.2,
                },
            )
            if response.status_code != 200:
                logger.error(
                    f"[prompt_refactor] LLM call to {url} returned HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
                return None
            return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error(
            f"[prompt_refactor] LLM call to {url} failed ({type(exc).__name__}: {exc})."
        )
        return None



async def refactor_prompt(
    prompt: str,
    agent_type: str,
    organization_id: Optional[int] = None,
) -> str:
    """Rewrite *prompt* for the given *agent_type* using an LLM.

    Priority:
      1. API key saved in the org's Prompt Refactor Model config page.
      2. AGENT_BUILDER_LLM_API_KEY / OPENAI_API_KEY env var fallback.

    Returns the original prompt unchanged on any failure so agent creation
    never hard-fails.

    Args:
        prompt: The original voice-call-biased node prompt.
        agent_type: One of ``"chat"`` or ``"call_and_chat"``.
        organization_id: The org whose stored key should be used first.
    """
    if not prompt or not prompt.strip():
        return prompt

    system_prompt = _SYSTEM_PROMPTS.get(agent_type)
    if not system_prompt:
        return prompt  # nothing to do for inbound / outbound call agents

    # ── 1. Try org's stored key from the Prompt Refactor Model config page ─
    endpoint: Optional[_LLMEndpoint] = None
    if organization_id is not None:
        try:
            from api.routes.prompt_refactor_config import get_prompt_refactor_api_key
            stored_key = await get_prompt_refactor_api_key(organization_id)
            if stored_key:
                endpoint = _LLMEndpoint(
                    base_url=_FALLBACK_BASE_URL,
                    api_key=stored_key,
                    model=_FALLBACK_MODEL,
                )
        except Exception as exc:
            logger.warning(f"[prompt_refactor] Could not read stored key: {exc}")

    # ── 2. Fall back to env var ────────────────────────────────────────────
    if endpoint is None:
        if not _FALLBACK_API_KEY:
            logger.warning(
                "[prompt_refactor] No API key configured. "
                "Go to Build → Prompt Refactor Model and add your OpenAI key."
            )
            return prompt
        endpoint = _LLMEndpoint(
            base_url=_FALLBACK_BASE_URL,
            api_key=_FALLBACK_API_KEY,
            model=_FALLBACK_MODEL,
        )

    logger.debug(
        f"[prompt_refactor] Rewriting {len(prompt)}-char prompt for "
        f"agent_type={agent_type!r} via {endpoint.base_url} model={endpoint.model!r}"
    )

    result = await _call_chat_completions(endpoint, system_prompt, prompt)
    if result is None:
        logger.warning(
            "[prompt_refactor] LLM rewrite failed; using original prompt."
        )
        return prompt

    logger.debug(
        f"[prompt_refactor] Rewrite complete: {len(prompt)} → {len(result)} chars."
    )
    return result


async def refactor_agent_node_chat_prompt(
    prompt: str,
    organization_id: Optional[int] = None,
) -> str:
    """Generate a chat-only optimised version of an agent node prompt.

    Used when building a call_and_chat workflow: the original call-optimised
    prompt is preserved as ``prompt`` and this function produces ``prompt_chat``
    which is optimised for text-chat sessions only.

    Returns the original prompt unchanged on any failure.
    """
    if not prompt or not prompt.strip():
        return prompt

    # ── 1. Try org's stored key ────────────────────────────────────────────
    endpoint: Optional[_LLMEndpoint] = None
    if organization_id is not None:
        try:
            from api.routes.prompt_refactor_config import get_prompt_refactor_api_key
            stored_key = await get_prompt_refactor_api_key(organization_id)
            if stored_key:
                endpoint = _LLMEndpoint(
                    base_url=_FALLBACK_BASE_URL,
                    api_key=stored_key,
                    model=_FALLBACK_MODEL,
                )
        except Exception as exc:
            logger.warning(f"[prompt_refactor] Could not read stored key: {exc}")

    # ── 2. Fall back to env var ────────────────────────────────────────────
    if endpoint is None:
        if not _FALLBACK_API_KEY:
            logger.warning(
                "[prompt_refactor] No API key for agent node chat prompt generation. "
                "Go to Build → Prompt Refactor Model and add your OpenAI key."
            )
            return prompt
        endpoint = _LLMEndpoint(
            base_url=_FALLBACK_BASE_URL,
            api_key=_FALLBACK_API_KEY,
            model=_FALLBACK_MODEL,
        )

    logger.debug(
        f"[prompt_refactor] Generating chat-only agent node prompt "
        f"({len(prompt)} chars) via {endpoint.base_url} model={endpoint.model!r}"
    )
    result = await _call_chat_completions(endpoint, _SYSTEM_AGENT_NODE_CHAT_ONLY, prompt)
    if result is None:
        logger.warning(
            "[prompt_refactor] Agent node chat prompt generation failed; using original."
        )
        return prompt
    logger.debug(
        f"[prompt_refactor] Agent node chat prompt: {len(prompt)} → {len(result)} chars."
    )
    return result


async def refactor_call_prompt(
    prompt: str,
    organization_id: Optional[int] = None,
) -> str:
    """Enhance an existing call-optimised prompt with data-collection quality rules.

    Adds spelling instructions, digit-by-digit confirmations, repeat-back
    confirmation, and one-question-at-a-time flow rules using the
    _SYSTEM_CALL_REFACTOR system prompt.

    Returns the original prompt unchanged on any failure.
    """
    if not prompt or not prompt.strip():
        return prompt

    # ── 1. Try org's stored key ────────────────────────────────────────────
    endpoint: Optional[_LLMEndpoint] = None
    if organization_id is not None:
        try:
            from api.routes.prompt_refactor_config import get_prompt_refactor_api_key
            stored_key = await get_prompt_refactor_api_key(organization_id)
            if stored_key:
                endpoint = _LLMEndpoint(
                    base_url=_FALLBACK_BASE_URL,
                    api_key=stored_key,
                    model=_FALLBACK_MODEL,
                )
        except Exception as exc:
            logger.warning(f"[prompt_refactor] Could not read stored key: {exc}")

    # ── 2. Fall back to env var ────────────────────────────────────────────
    if endpoint is None:
        if not _FALLBACK_API_KEY:
            logger.warning(
                "[prompt_refactor] No API key for call prompt refactoring. "
                "Go to Build → Prompt Refactor Model and add your OpenAI key."
            )
            return prompt
        endpoint = _LLMEndpoint(
            base_url=_FALLBACK_BASE_URL,
            api_key=_FALLBACK_API_KEY,
            model=_FALLBACK_MODEL,
        )

    logger.debug(
        f"[prompt_refactor] Refactoring call prompt "
        f"({len(prompt)} chars) via {endpoint.base_url} model={endpoint.model!r}"
    )
    result = await _call_chat_completions(endpoint, _SYSTEM_CALL_REFACTOR, prompt)
    if result is None:
        logger.warning(
            "[prompt_refactor] Call prompt refactor failed; using original."
        )
        return prompt
    logger.debug(
        f"[prompt_refactor] Call prompt refactor: {len(prompt)} → {len(result)} chars."
    )
    return result

async def refactor_workflow_prompts(
    workflow_def: dict,
    agent_type: str,
    organization_id: Optional[int] = None,
    # Kept for backward compat but no longer used:
    ai_model_config: Optional[object] = None,
) -> None:
    """Rewrite every prompted node's prompts in *workflow_def* in-place.

    All four prompted node types (startCall, agentNode, endCall, globalNode)
    receive the same dual-prompt treatment for every agent type:

    For ``call`` agents:
    - ``prompt`` is refined via LLM (spelling, digit confirmation, repeat-back,
      one-at-a-time rules). ``channel_mode`` stays ``"call"``.

    For ``call_and_chat`` agents:
    - ``prompt`` is refined via the call LLM refactor (same quality rules).
    - ``prompt_chat`` is generated as a chat-only version of the original prompt.
    - ``channel_mode`` is set to ``"call_and_chat"``.

    For ``chat`` agents:
    - ``prompt`` is refactored to chat-only.
    - ``prompt_chat`` is set to the same chat-only value.
    - ``channel_mode`` is set to ``"chat"``.

    Args:
        workflow_def: The full workflow definition dict (mutated in-place).
        agent_type: ``"inbound"``, ``"outbound"``, ``"chat"``, or
            ``"call_and_chat"``.
        organization_id: The org whose stored Prompt Refactor key should be used.
    """
    if not workflow_def or "nodes" not in workflow_def:
        return
    # Normalise legacy call types to a single "call" category.
    _call_types = {"call", "inbound", "outbound"}
    if agent_type not in _call_types | {"chat", "call_and_chat"}:
        return

    # All node types that carry a prompt field we care about.
    _PROMPTED_NODE_TYPES = {"startCall", "agentNode", "endCall", "globalNode"}

    for node in workflow_def["nodes"]:
        node_data = node.get("data")
        if not isinstance(node_data, dict):
            continue
        node_type = node.get("type")
        if node_type not in _PROMPTED_NODE_TYPES:
            continue
        prompt: str = node_data.get("prompt", "")
        if not prompt:
            continue

        # End nodes carry closing system instructions, not data collection steps.
        # Call mode end node prompts are kept untouched (already voice-optimised).
        # Chat mode end node prompts adapt call terminology to chat terminology deterministically.
        if node_type == "endCall":
            if agent_type in _call_types:
                pass
            elif agent_type == "call_and_chat":
                node_data["channel_mode"] = "call_and_chat"
                node_data["prompt_chat"] = refactor_end_node_chat_prompt(prompt)
            elif agent_type == "chat":
                refactored_end = refactor_end_node_chat_prompt(prompt)
                node_data["prompt"] = refactored_end
                node_data["channel_mode"] = "chat"
                node_data["prompt_chat"] = refactored_end
            continue

        if agent_type in _call_types:
            # Call-only: refine the call prompt with quality rules.
            # channel_mode stays "call" (DTO default — no need to set it).
            node_data["prompt"] = await refactor_call_prompt(
                prompt,
                organization_id=organization_id,
            )

        elif agent_type == "call_and_chat":
            # Refine call prompt + generate separate chat-only prompt.
            node_data["channel_mode"] = "call_and_chat"
            node_data["prompt"] = await refactor_call_prompt(
                prompt,
                organization_id=organization_id,
            )
            node_data["prompt_chat"] = await refactor_agent_node_chat_prompt(
                prompt,
                organization_id=organization_id,
            )

        elif agent_type == "chat":
            # Refactor prompt to chat-only.
            refactored = await refactor_prompt(
                prompt,
                agent_type,
                organization_id=organization_id,
            )
            node_data["prompt"] = refactored
            node_data["channel_mode"] = "chat"
            node_data["prompt_chat"] = refactored

