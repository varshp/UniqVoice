"""
agents/sub_agents/trend_scout.py
--------------------------------
Role: The ideation step. Searches for recent news around topic_seeds, 
      proposes 2-3 specific angles, and asks the user to pick one.

Governed by: specs/SPEC.md Section 11.2.
Milestone:   M5
Eval case:   trend_scout_fallback_001

State reads:  topic_seeds
State writes: topic_candidates, topic
"""

import json
import logging
import os
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import request_input
from google.genai import types

from agents.mcp_tools import search_toolset

logger = logging.getLogger(__name__)

_MODEL = os.getenv("TREND_SCOUT_MODEL", "gemini-2.5-flash")

_INSTRUCTION = """\
You are a proactive content ideation assistant.

Your task:
1. Review the user's explicit request and their broad writing lanes (topic_seeds):
   Explicit Request: "{explicit_topic_request}"
   Topic Seeds: {topic_seeds}

2. PRECEDENCE RULE: If an Explicit Request is provided and is not empty, you MUST treat THAT as the primary subject. 
   Search the news for that specific topic and propose 3 candidate angles about it (or use it directly).
   DO NOT override the explicit request with the Topic Seeds.
   CRITICAL: Every candidate angle you propose MUST explicitly include the subject (e.g., "SpaceX post-IPO — timing: invest now vs wait for lock-up expiry"). Never generate an angle that drops the core subject.

3. If the Explicit Request is empty, then use the Topic Seeds to find news and discussions 
   from the past 7 days. Identify 3 timely, high-traction themes/angles based on the seeds. 
   If nothing is trending, propose 3 evergreen angles based strictly on the seeds.
   CRITICAL: Every candidate MUST explicitly include the broad topic seed it is based on.

4. Present the 3 candidates to the user using the `request_input` tool. 
   CRITICAL: You MUST format the `message` argument of the `request_input` tool as a strictly valid JSON array of exactly 3 objects matching this schema:
   [
     {{
       "title": "<A punchy, specific title for the angle (max 10 words)>",
       "description": "<A 1-sentence summary of what the article will cover>",
       "reasoning": "<1-2 sentences on why this angle is compelling right now>"
     }},
     {{ "title": "...", "description": "...", "reasoning": "..." }},
     {{ "title": "...", "description": "...", "reasoning": "..." }}
   ]
   Do NOT include any other conversational text in the `message` argument. The `message` must be ONLY the raw JSON array string.
5. Once the user replies with their choice, finalize your turn.

You MUST output your final result as ONLY a JSON object matching this schema exactly:
{{
  "topic_candidates": [
    {{
      "title": "<A punchy, specific title for the angle (max 10 words)>",
      "description": "<A 1-sentence summary of what the article will cover>",
      "reasoning": "<1-2 sentences on why this angle is compelling right now>"
    }},
    {{
      "title": "...",
      "description": "...",
      "reasoning": "..."
    }},
    {{
      "title": "...",
      "description": "...",
      "reasoning": "..."
    }}
  ],
  "topic": "<The final topic angle the user chose>"
}}

Output ONLY the JSON object. No markdown fences, no preamble.
"""

async def _bootstrap_topic_seeds(callback_context: CallbackContext) -> None:
    """
    before_agent_callback: Captures explicit user requests and bootstraps topic_seeds.
    """
    # Always ensure explicit_topic_request exists in state so the template doesn't fail
    if "explicit_topic_request" not in callback_context.state:
        callback_context.state["explicit_topic_request"] = ""

    # Capture explicit request from the user message if it exists
    if callback_context.user_content and callback_context.user_content.parts:
        text = " ".join(p.text for p in callback_context.user_content.parts if p.text).strip()
        if text:
            callback_context.state["explicit_topic_request"] = text
            logger.info("[trend_scout] Captured explicit topic request: %s", text)

    if "topic_seeds" not in callback_context.state:
        seeds = ["B2B software sales", "AI marketing automation"]
        callback_context.state["topic_seeds"] = seeds
        logger.info("[trend_scout] Bootstrapped default topic_seeds: %s", seeds)

async def _unpack_scout_response(callback_context: CallbackContext) -> Optional[types.Content]:
    """
    after_agent_callback: Unpacks the JSON response into 'topic_candidates' 
    and 'topic'.
    """
    raw = callback_context.state.get("trend_scout_raw", "")
    if not raw:
        return None

    try:
        if raw.startswith("```json"):
            raw = raw[7:-3]
        elif raw.startswith("```"):
            raw = raw[3:-3]
            
        # Fix common LLM mistake of escaping single quotes in JSON
        raw = raw.replace("\\'", "'")
            
        data = json.loads(raw.strip())
        
        callback_context.state["topic_candidates"] = data.get("topic_candidates", [])
        callback_context.state["topic"] = data.get("topic", "")
        
    except Exception as e:
        logger.error("[trend_scout] Failed to parse JSON: %s. Raw: %s", e, raw)
        # Fallback to the raw text
        callback_context.state["topic"] = raw
        
    return None

trend_scout_agent = LlmAgent(
    name="trend_scout",
    model=_MODEL,
    instruction=_INSTRUCTION,
    output_key="trend_scout_raw",
    tools=[search_toolset, request_input],
    before_agent_callback=_bootstrap_topic_seeds,
    after_agent_callback=_unpack_scout_response,
    description=(
        "M5: Ideation agent. Finds trends, proposes candidates, asks user via request_input, "
        "and sets 'topic_candidates' and 'topic'."
    ),
)
