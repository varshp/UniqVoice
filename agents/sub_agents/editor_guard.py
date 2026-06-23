"""
agents/sub_agents/editor_guard.py
---------------------------------
Role: The security and quality step. Cleans up AI slop, removes filler,
      and performs a final scan for PII (emails, phone numbers, etc.) before
      the article is finalized.

Governed by: specs/SPEC.md Section 11.6.
Milestone:   M4
Eval case:   editor_removes_pii_001

State reads:  draft
State writes: final_article, policy_notes

Note on Separation of Concerns:
This agent handles "execution" logic (reading text, following instructions to clean).
The "governance" logic (structural network checks, ToU semantic checks) is strictly
enforced outside the agent loop via agents/callbacks/policy.py.
"""

import json
import logging
import os
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

logger = logging.getLogger(__name__)

_MODEL = os.getenv("EDITOR_GUARD_MODEL", "gemini-2.5-pro")

_INSTRUCTION = """\
You are the final editor and security guard for this article.

Your tasks:
1. Slop-clean: Read the draft and remove any AI filler, hedging, or clichés 
   (e.g., "In today's rapidly evolving landscape", "It is important to note").
2. Security Scan: Identify and completely REMOVE any Personally Identifiable 
   Information (PII) such as email addresses, phone numbers, or private URLs.
3. Record: If you removed any PII, describe exactly what you stripped. 
   If none, output "No PII stripped."

Draft:
{draft}

Output your result as ONLY a JSON object matching this schema exactly:
{{
  "final_article": "<The cleaned, PII-free markdown text>",
  "policy_notes_addition": "<A short note about what PII was stripped, or 'No PII stripped.'>"
}}

Output ONLY the JSON object. No markdown fences, no preamble.
"""

async def _extract_final_article(callback_context: CallbackContext) -> Optional[types.Content]:
    """
    after_agent_callback: Unpacks the JSON response into 'final_article'
    and appends to 'policy_notes' if PII was stripped.
    """
    raw = callback_context.state.get("editor_guard_raw", "")
    if not raw:
        return None

    try:
        # Strip markdown fences just in case the model adds them
        if raw.startswith("```json"):
            raw = raw[7:-3]
        elif raw.startswith("```"):
            raw = raw[3:-3]
            
        data = json.loads(raw.strip())
        
        callback_context.state["final_article"] = data.get("final_article", "")
        
        notes = data.get("policy_notes_addition", "")
        if notes and "no pii" not in notes.lower():
            current = callback_context.state.get("policy_notes", "")
            prefix = "\n" if current else ""
            callback_context.state["policy_notes"] = current + f"{prefix}- [editor_guard] {notes}"
            logger.info("[editor_guard] Appended PII note to policy_notes.")
            
    except Exception as e:
        logger.error("[editor_guard] Failed to parse JSON: %s. Raw: %s", e, raw)
        # Fallback to the raw text so we don't drop the article completely
        callback_context.state["final_article"] = raw
        
editor_guard_agent = LlmAgent(
    name="editor_guard",
    model=_MODEL,
    instruction=_INSTRUCTION,
    output_key="editor_guard_raw",
    after_agent_callback=_extract_final_article,
    description=(
        "M4: Security and quality gate. Cleans slop and strips PII from the draft. "
        "Writes final_article and updates policy_notes."
    ),
)
