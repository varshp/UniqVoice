"""
agents/sub_agents/drafter.py
------------------------------
Role: Writes the full article draft from the angle_brief outline.

Governed by: specs/SPEC.md Section 11.5.
Milestone:   M2 — activated with {angle_brief} only (the JSON string from angle_finder).
             M6 — add {voice_profile} + {tone_notes} once voice_profile_builder exists.

State reads  (M2 — keys that exist by this milestone):
  angle_brief   — JSON from angle_finder: {angle, why_new, outline, must_include}

State reads  (future milestones — NOT active yet):
  voice_profile — extracted during onboarding  [M6, from voice_profile_builder]
  tone_notes    — free-text voice summary       [M6, from voice_profile_builder]

State writes: draft  (the full article as a Markdown string)

Model: gemini-2.5-flash  (cheaper/faster; reasoning was done in angle_finder — Section 6).
Tools: none — drafts purely from the angle_brief passed in.

Note on {angle_brief} substitution:
  ADK substitutes {angle_brief} with the raw JSON string that angle_finder wrote.
  The model receives the full JSON and is instructed to parse it inline.
  In M6, once voice_profile is available, the instruction gains the voice section.
"""

import json
import logging
import os

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)

_MODEL = os.getenv("DRAFTER_MODEL", "gemini-2.5-flash")

# ── M2 Instruction — uses only {angle_brief} ─────────────────────────────────
# Keys guarded as prose (not live {braces}) until their producers exist:
#
#   {voice_profile} → produced by voice_profile_builder (M6).
#   {tone_notes}    → also from voice_profile_builder (M6).
#
# Instruction intent (Section 11.5):
# "Write the article to the outline AND in this exact voice — match the tone,
#  rhythm, vocabulary, and rhetorical moves; avoid the listed clichés."
_INSTRUCTION = """\
You are a skilled content writer. Your job is to write a complete, \
publication-ready article from the brief below.

PRIMARY SUBJECT: {explicit_topic_request}

── ARTICLE BRIEF (JSON) ────────────────────────────────────────────────────────
{angle_brief}
────────────────────────────────────────────────────────────────────────────────

Parse the JSON above to extract:
  - "angle"        → your working title / thesis
  - "why_new"      → the differentiated perspective to argue throughout
  - "outline"      → the beats to follow in order
  - "must_include" → elements that MUST appear somewhere in the article

── VOICE ───────────────────────────────────────────────────────────────────────
Voice Profile: {voice_profile}
Tone Notes: {tone_notes}

── YOUR TASK ───────────────────────────────────────────────────────────────────
Write the full article following the outline beats in order.
CRITICAL: Ensure the entire article is specifically about the PRIMARY SUBJECT.

Non-negotiable rules:
- Cover every item in must_include.
- Argue the "why_new" perspective throughout — do not drift into the commodity take.
- STYLE OVER CHECKLIST: Treat the voice_profile's "vocabulary" list as a signal of the writer's register and style. Do NOT treat it as a checklist of words to force into the text. Only use those specific words if they fit the subject naturally (e.g., do not force marketing terms like 'go-to-market' into an unrelated finance piece).
- Format: clean Markdown (# for title, ## for sections, prose paragraphs — no \
bullet dumps).
- Length: 800–1 200 words.
- Do NOT invent statistics or quotes you cannot support from the brief.
- Do NOT fabricate real-world publications (e.g., The Atlantic, The Athletic, NYT) or invent sources. If you need an example, use a hypothetical scenario.
- Do NOT open with "In today's rapidly evolving..." or any AI cliché.
- Output the article text ONLY — no preamble, no JSON wrapper.
"""

# ── Agent definition ──────────────────────────────────────────────────────────
# output_key='draft' is the single state write for this agent.
# ADK copies the model's final text response verbatim into:
#   session.state['draft']
# editor_guard (M4) then reads {draft} for slop-cleaning and PII stripping.
drafter_agent = LlmAgent(
    name="drafter",
    model=_MODEL,
    instruction=_INSTRUCTION,
    output_key="draft",
    description=(
        "M2: writes a full article from the angle_brief JSON. "
        "Reads {angle_brief}; writes draft (Markdown string). "
        "voice_profile and tone_notes added in M6."
    ),
)
