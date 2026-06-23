"""
agents/orchestrator.py
----------------------
Role: Wires pipeline sub-agents into a SequentialAgent that ADK's runner
      executes in order, passing shared session state between them.

Governed by: specs/SPEC.md Section 5 (System Architecture) and Section 11.
Milestone:   M1 — single agent (serp_analyst) to prove output_key + state.  ✓
             M2 — chain serp_analyst → angle_finder → drafter.              ✓
             M4 — add editor_guard and policy callback.                     ✓
             M5 — add trend_scout at the front.

──────────────────────────────────────────────────────────────────────────────
HOW SequentialAgent PASSES STATE (the "baton")
──────────────────────────────────────────────────────────────────────────────
ADK's SequentialAgent runs each sub_agent one at a time in the list order.
After each sub_agent finishes, its output_key value is merged into the shared
InvocationContext.session.state dict. The next sub_agent's instruction template
can then reference that value with {key_name} — ADK substitutes it automatically
before sending the prompt to the model.

  sub_agent A  →  output_key='foo'  →  session.state['foo'] = A's output
  sub_agent B  →  instruction uses '{foo}'  →  ADK fills in the value
  sub_agent B  →  output_key='bar'  →  session.state['bar'] = B's output
  ...

No sub_agent writes to state directly. The only mutation path is output_key.
This keeps each agent side-effect-free and individually testable.

Full state schema (Section 10 of specs/SPEC.md):
  topic_seeds       → trend_scout      → topic_candidates, topic   [M5]
  topic             → serp_analyst     → serp_findings              [M1 ✓]
  serp_findings     → angle_finder     → angle_brief                [M2]
  angle_brief       → drafter          → draft                      [M2]
  draft             → editor_guard     → final_article, policy_notes [M4]

HITL gates (two human approvals — Section 4):
  Gate 1: human selects topic from trend_scout candidates            [M5]
  Gate 2: human approves final_article before any publish action     [M4]

Usage:
  agents-cli playground   # opens ADK web UI; inspect State tab after each run
──────────────────────────────────────────────────────────────────────────────
"""

from google.adk.agents import SequentialAgent

# ── M2: serp_analyst → angle_finder → drafter ────────────────────────────────
from agents.sub_agents.serp_analyst import serp_analyst_agent
from agents.sub_agents.angle_finder import angle_finder_agent
from agents.sub_agents.drafter import drafter_agent

# ── M4: add editor_guard ─────────────────────────────────────────────────────
from agents.sub_agents.editor_guard import editor_guard_agent

# ── M7: add report_builder ───────────────────────────────────────────────────
from agents.sub_agents.report_builder import report_builder_agent

import json
import logging
import os
from google.adk.agents.callback_context import CallbackContext

logger = logging.getLogger(__name__)

async def load_voice_profile(callback_context: CallbackContext) -> None:
    """
    before_agent_callback on the root SequentialAgent.
    Loads M6 voice profile if it exists. Merges topic_seeds instead of overwriting.
    """
    profile_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "profile",
        "voice_profile.json"
    )
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Populate state
            if "voice_profile" in data:
                callback_context.state["voice_profile"] = data["voice_profile"]
            if "tone_notes" in data:
                callback_context.state["tone_notes"] = data["tone_notes"]
                
            # Merge topic_seeds
            if "topic_seeds" in data:
                profile_seeds = data["topic_seeds"]
                current_seeds = callback_context.state.get("topic_seeds", [])
                
                # Deduplicate while preserving order
                merged = list(current_seeds)
                for seed in profile_seeds:
                    if seed not in merged:
                        merged.append(seed)
                        
                callback_context.state["topic_seeds"] = merged
                
            logger.info("[orchestrator] Loaded M6 voice profile and merged topic_seeds.")
        except Exception as e:
            logger.error("[orchestrator] Failed to load voice profile: %s", e)

# ── M5: prepend trend_scout ──────────────────────────────────────────────────
from agents.sub_agents.trend_scout import trend_scout_agent

# ── SequentialAgent — M2 pipeline ────────────────────────────────────────────
# Type a topic in the playground chat input. The bootstrap callback in
# serp_analyst writes it to state['topic'], then the baton passes:
#   topic → serp_analyst → serp_findings → angle_finder → angle_brief → drafter → draft
# Open the State tab after the run — all three keys should appear in order.

root_agent = SequentialAgent(
    name="content_pipeline",
    description=(
        "Voice-aware content engine. "
        "M5: trend_scout → serp_analyst → angle_finder → drafter → editor_guard "
        "(topic_candidates → topic → draft → final_article). "
        "Full pipeline assembled milestone by milestone."
    ),
    before_agent_callback=load_voice_profile,
    sub_agents=[
        # ── M5: prepend at front ──────────────────────────────────────────────
        trend_scout_agent,   # reads: topic_seeds  |  writes: topic_candidates, topic

        # ── ACTIVE in M2/M4 ───────────────────────────────────────────────────
        serp_analyst_agent,   # reads: topic                | writes: serp_findings
        angle_finder_agent,   # reads: topic, serp_findings | writes: angle_brief
        drafter_agent,        # reads: angle_brief          | writes: draft

        # ── M4: add next ──────────────────────────────────────────────────────
        editor_guard_agent,  # reads: draft  |  writes: final_article, policy_notes

        # ── M7: final report generation ───────────────────────────────────────
        report_builder_agent, # reads: existing state  |  writes: run_report
    ],
)
