"""
agents/sub_agents/angle_finder.py
-----------------------------------
Role: The reasoning heart of the pipeline — finds a non-commodity article angle
      by comparing the SERP consensus against the topic and the user's knowledge.
      This is what makes the output different from generic AI content.

Governed by: specs/SPEC.md Section 11.4.
Milestone:   M2 — activated with {topic} + {serp_findings} only.
             M6 — add {topic_seeds} (from onboarding) once voice_profile_builder exists.
             M6 — add {knowledge_base_notes} once the KB loader is wired.
Eval case:   angle_is_non_commodity_001 (specs/evals/).

State reads  (M2 — keys that exist by this milestone):
  topic          — the article topic (set by bootstrap callback or trend_scout)
  serp_findings  — JSON from serp_analyst: {sources, common_claims}

State reads  (future milestones — NOT active yet, would cause "Context variable
              not found" if used as live {braces} before their producers exist):
  topic_seeds            — user's content lanes  [M6, from voice_profile_builder]
  knowledge_base_notes   — proprietary KB text   [M6, from KB loader in orchestrator]

State writes: angle_brief  (the non-commodity plan as JSON)

angle_brief schema (Section 10):
  angle:        string    — the differentiated angle
  why_new:      string    — how it differs from common_claims
  outline:      [string]  — article section headings / beats
  must_include: [string]  — e.g. "≥1 product mention", "≥1 service mention"

Model: gemini-2.5-pro  (reasoning step — Section 6 of specs/SPEC.md).
Tools: none — reasons over state; no external calls.
"""

import json
import logging
import os

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)

_MODEL = os.getenv("ANGLE_FINDER_MODEL", "gemini-2.5-pro")

def _append_warning(state: dict, msg: str) -> None:
    current = state.get("policy_notes", "")
    prefix = "\n" if current else ""
    state["policy_notes"] = current + f"{prefix}- [System Warning] {msg}"

def _bootstrap_serp_findings(callback_context: CallbackContext) -> None:
    state = callback_context.state
    if not state.get("serp_findings"):
        logger.warning("[angle_finder] serp_findings missing! Bootstrapping fallback.")
        state["serp_findings"] = '{"sources": [], "common_claims": ["Fallback claim 1", "Fallback claim 2"]}'
        _append_warning(state, "serp_findings missing; used fallback commodity consensus.")
    if not state.get("explicit_topic_request"):
        state["explicit_topic_request"] = "Fallback primary subject"
        _append_warning(state, "explicit_topic_request missing; used fallback.")
    if not state.get("topic"):
        state["topic"] = "Fallback chosen angle"
        _append_warning(state, "topic missing; used fallback.")
    return None


# ── M2 Instruction — uses only {topic} and {serp_findings} ───────────────────
# Keys guarded as prose (not live {braces}) until their producers exist:
#
#   {topic_seeds}          → produced by voice_profile_builder (M6).
#                            When M6 lands, replace the static text below with
#                            the live brace and the model will receive the user's
#                            actual content lanes.
#
#   {knowledge_base_notes} → produced by a KB-loader step in orchestrator (M6).
#                            When M6 lands, replace the static text below with
#                            the live brace so the model reads knowledge_base/notes.md.
#
# Instruction intent (Section 11.4):
# "Given the commodity consensus and the user's proprietary knowledge, find an
#  angle that adds something NEW."
_INSTRUCTION = """\
You are a strategic content angle finder. Your job is to identify a differentiated,
non-commodity article angle — something that ADDS to the conversation rather than
repeating what already ranks.

PRIMARY SUBJECT:
{explicit_topic_request}

CHOSEN ANGLE:
{topic}

COMPETITIVE CONSENSUS (what the top-ranking articles already say):
{serp_findings}

USER'S CONTENT LANES:
[Not yet available — topic_seeds will be injected here in M6 once onboarding
is built. For now, infer the user's likely focus from the topic itself.]

USER'S PROPRIETARY KNOWLEDGE BASE:
[Not yet available — knowledge_base/notes.md will be injected here in M6.
For now, reason purely from the competitive consensus above and the topic.]

Your task:
1. Study the common_claims in the competitive consensus.
2. Identify the dominant "commodity" take — the angle everyone already covers.
3. Find a differentiated angle that reframes, extends, or contradicts that take
   with a fresh perspective. 
   CRITICAL: Your final angle MUST keep the Primary Subject central. Use the Chosen Angle only as the lens through which to explore the Primary Subject. Do NOT drop the Primary Subject.
4. Draft a tight outline (5–7 beats) that delivers on the angle.
5. List must_include items (at minimum: a concrete example and a clear takeaway).

Output ONLY valid JSON matching this schema exactly:
{{
  "angle": "<the differentiated angle as a punchy working title>",
  "why_new": "<one paragraph: how this differs from the common_claims>",
  "outline": [
    "<beat 1>",
    "<beat 2>",
    "<beat 3>",
    "<beat 4>",
    "<beat 5>"
  ],
  "must_include": [
    "<required element 1>",
    "<required element 2>"
  ]
}}

Rules:
- The angle MUST differ meaningfully from all common_claims (eval requirement).
- Do NOT be generic. "Use AI to do X faster" is not an acceptable angle.
- Do NOT fabricate real-world publications or invent sources for the outline or must_include.
- Output ONLY the JSON — no markdown fences, no preamble, no explanation.
"""

# ── Agent definition ──────────────────────────────────────────────────────────
# output_key='angle_brief' is the single state write for this agent.
# ADK copies the model's final text response verbatim into:
#   session.state['angle_brief']
# drafter then receives {angle_brief} as the full JSON string.
angle_finder_agent = LlmAgent(
    name="angle_finder",
    model=_MODEL,
    instruction=_INSTRUCTION,
    # ── before_agent_callback ──────────────────────────────────────────────────
    before_agent_callback=_bootstrap_serp_findings,
    # ── output_key ─────────────────────────────────────────────────────────────
    # writes its JSON to session.state['angle_brief'].
    output_key="angle_brief",
    description=(
        "M2: finds a non-commodity angle from the SERP consensus. "
        "Reads {topic} + {serp_findings}; writes angle_brief JSON. "
        "topic_seeds and knowledge_base_notes added in M6."
    ),
)
