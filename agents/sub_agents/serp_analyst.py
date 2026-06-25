"""
agents/sub_agents/serp_analyst.py
----------------------------------
Role: Researches the top-ranking articles for the chosen topic, summarises what
      they collectively say, and extracts the "commodity consensus" that the next
      pipeline agent (angle_finder) will deliberately differentiate against.

Governed by: specs/SPEC.md Section 11.3.
Milestone:   M1 — skeleton with output_key + topic bootstrap callback.
             M3 — real search + fetch MCP tools wired in.  ✓
Eval case:   serp_reads_top_pages_001 (specs/evals/).

──────────────────────────────────────────────────────────────────────────────
HOW output_key WRITES TO session.state  (the core M1 mechanic)
──────────────────────────────────────────────────────────────────────────────
When an LlmAgent has output_key='serp_findings', ADK does this automatically
after the model produces its final response:

  1. The LlmAgent finishes its last LLM call and emits a final Event.
  2. ADK's event-processing loop calls _process_model_response() on the event.
  3. It joins all non-thought text parts into a single string called `result`.
  4. It writes:  event.actions.state_delta['serp_findings'] = result
  5. On the next tick the runner merges state_delta into the live session.state,
     so session.state['serp_findings'] now holds the agent's full text output.
  6. The next sub-agent in the SequentialAgent receives that updated state and
     can reference {serp_findings} inside its own instruction template.

The agent itself does NOT call session.state directly — it just returns text.
ADK's output_key plumbing handles all the state mutation, keeping each sub-agent
free of side-effects and individually testable.

Source: google/adk/agents/llm_agent.py, _process_model_response(), line ~954:
  event.actions.state_delta[self.output_key] = result
──────────────────────────────────────────────────────────────────────────────

──────────────────────────────────────────────────────────────────────────────
M1 TOPIC BOOTSTRAP — before_agent_callback
──────────────────────────────────────────────────────────────────────────────
In the full pipeline (M5+), state['topic'] is written by trend_scout after
the human picks an angle (HITL Gate 1).  In M1, trend_scout doesn't exist
yet, so state['topic'] is never set — causing ADK's instruction renderer to
throw "Context variable not found: topic" before the model is even called.

The before_agent_callback runs BEFORE the instruction template is rendered.
It solves the bootstrap problem:
  - If state['topic'] is already set (future M5 normal path) → do nothing.
  - If state['topic'] is missing (M1 dev-UI path) → read the user's chat
    message and write it to state['topic'] so the instruction can render.

Callback API (google.adk.agents.callback_context.CallbackContext):
  ctx.user_content          → types.Content (the user's latest message)
  ctx.user_content.parts    → list[types.Part]
  ctx.user_content.parts[n].text  → the text of the nth Part
  ctx.state['key'] = value  → writes to the writable State (delta-aware;
                               ADK persists the delta with the next Event)

Return value of the callback:
  None          → let the agent run normally (always what we want here)
  types.Content → skip the LLM call entirely and return that content instead

This callback is removed (or converted to a no-op) in M5 when trend_scout
is wired and provides state['topic'] before serp_analyst runs.
──────────────────────────────────────────────────────────────────────────────

State reads:  topic          — set by trend_scout (M5+) or bootstrapped here (M1)
State writes: serp_findings  — JSON string matching the schema below

serp_findings schema (Section 10 of specs/SPEC.md):
  {
    "sources":       [{"url": string, "summary": string}],
    "common_claims": [string]
  }

Model: gemini-2.5-flash  (cheap/fast step — Section 6 of specs/SPEC.md).
Tools: NONE in M1 — placeholder output only.
       M3 adds: search MCP (tavily-mcp) + fetch MCP (mcp-server-fetch).

Security note: in M3, every fetch call will be intercepted by the after-tool
callback in agents/callbacks/policy.py before its content enters state.
"""

import logging
import os
import yaml
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from agents.callbacks.policy import fetch_before_policy_callback, fetch_after_policy_callback
from agents.mcp_tools import search_toolset, fetch_toolset

logger = logging.getLogger(__name__)

# Load reputable domains for soft ranking
_config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "allowlist.yaml",
)
_reputable_domains_str = ""
if os.path.exists(_config_path):
    with open(_config_path, "r", encoding="utf-8") as f:
        _allowlist_config = yaml.safe_load(f) or {}
        _allowed = _allowlist_config.get("allowed_domains", [])
        if _allowed:
            _reputable_domains_str = ", ".join(_allowed)

# ── Model ──────────────────────────────────────────────────────────────────────
# Loaded from the environment so it can be overridden per deployment without
# touching code. Falls back to the spec default (Section 6) if not set.
_MODEL = os.getenv("SERP_ANALYST_MODEL", "gemini-2.5-flash")


# ── M1 Topic Bootstrap Callback ───────────────────────────────────────────────
def _bootstrap_topic(callback_context: CallbackContext) -> Optional[types.Content]:
    """
    before_agent_callback: ensures state['topic'] is populated before the
    instruction template is rendered.

    PARAMETER NAME — callback_context (not ctx)
    ─────────────────────────────────────────────
    ADK invokes before_agent_callback with a keyword argument, not positional:
        callback(callback_context=<CallbackContext instance>)
    Source: base_agent.py _handle_before_agent_callback(), line ~487:
        before_agent_callback_content = callback(callback_context=callback_context)
    The parameter name MUST match that keyword exactly.

    WHY THIS IS NEEDED IN M1
    ─────────────────────────
    ADK renders instruction templates (substituting {key} with session.state
    values) immediately before sending the prompt to the model.  If 'topic'
    is missing from state, instructions_utils.py raises:
        KeyError: "Context variable not found: `topic`."

    In the full pipeline (M5+), state['topic'] arrives via trend_scout →
    human HITL selection.  In M1, we bootstrap it from the user's chat input.

    WHAT IT DOES
    ─────────────
    1. Checks whether state['topic'] is already set.
       - YES → nothing to do; return None to let the agent run normally.
       - NO  → fall through to step 2.

    2. Extracts the text of the user's latest message from callback_context.user_content.
       user_content is a types.Content object:
         .parts          → list[types.Part]
         .parts[n].text  → str | None  (None for non-text parts like images)

    3. Joins all text parts into a single string, strips whitespace.
       If the user sent an empty message, falls back to a safe default so the
       agent can still run and produce a placeholder result.

    4. Writes the topic to callback_context.state['topic'].
       callback_context.state is the writable ADK State object (delta-aware).
       Writing to it here persists the delta with the next Event commit, so
       the value is immediately visible to the instruction renderer and to the
       State tab in the dev UI.

    RETURN VALUE
    ─────────────
    Always None → ADK runs the agent normally after the callback.
    Returning a types.Content here would skip the LLM call entirely, which is
    NOT what we want — we still want serp_analyst to run and write serp_findings.

    REMOVAL IN M5
    ──────────────
    When trend_scout is wired (M5), state['topic'] will always be populated
    before serp_analyst runs.  This callback becomes a no-op (the 'already set'
    branch always fires) and can be safely removed at that point.
    """
    # ── Already set (normal M5+ path, or user pre-seeded state) ──────────────
    if callback_context.state.get("topic"):
        logger.debug(
            "[serp_analyst] state['topic'] already set to %r — skipping bootstrap.",
            callback_context.state["topic"],
        )
        return None  # let the agent run with the existing topic

    # ── Not set: bootstrap from the user's latest chat message (M1 path) ─────
    topic: str = ""

    user_content: Optional[types.Content] = callback_context.user_content
    if user_content and user_content.parts:
        # Concatenate all text parts (non-text parts like images have .text=None).
        topic = " ".join(
            part.text for part in user_content.parts if part.text
        ).strip()

    if not topic:
        # Safety net: user sent a blank message or only non-text content.
        # Use a default so the agent still runs and demonstrates the state mechanic.
        topic = "AI marketing — bootstrapped default topic (send a real topic in chat)"
        logger.warning(
            "[serp_analyst] No text found in user message. "
            "Using default topic for M1 demo: %r",
            topic,
        )

    # Write to state — this is the ONLY state write in this callback.
    # callback_context.state is the writable State object; ADK merges this into
    # session.state automatically via the event delta mechanism.
    callback_context.state["topic"] = topic

    logger.info(
        "[serp_analyst] Bootstrap: wrote state['topic'] = %r from user message.",
        topic,
    )

    # Return None → ADK continues to run the agent normally.
    # The instruction renderer will now find 'topic' in state and substitute it.
    return None


# ── M3 Instruction (Real Research with MCP Tools) ───────────────────────────
# In M3 we replace the M1 placeholder with the real research prompt that uses
# the search + fetch MCP tools.
_INSTRUCTION = f"""\
You are a SERP research analyst.

Primary Subject: {{explicit_topic_request}}
Chosen Angle: {{topic}}

Step 1 — Search for the top-ranking articles and blog posts on this topic.
         Use 1–2 targeted search queries. 
         CRITICAL: Build your search queries by combining the Primary Subject AND the Chosen Angle. Ensure research stays strictly anchored to the Primary Subject.
         Identify at least 3–5 URLs.
         Optional Soft Ranking: Prefer these reputable domains if they appear in your search results: {_reputable_domains_str}

Step 2 — Fetch and read each URL. You MUST use the fetch tool to retrieve the actual page content. Do NOT rely on search snippets. For each page, write a 2–3 sentence summary of its main argument.

Step 3 — Identify the COMMON CLAIMS: the points almost every article makes.
         These are the 'commodity consensus' the next agent will go beyond.

Output ONLY valid JSON:
{{{{
  "sources": [{{{{"url": "<url>", "summary": "<2-3 sentence summary>"}}}}],
  "common_claims": ["<claim 1>", "<claim 2>"]
}}}}

Rules:
- At least 2 sources (eval case serp_reads_top_pages_001 requires this).
- At least 2 common_claims.
- Never invent content — only use what you actually fetched.
- Robustness: NEVER loop on unavailable sources. If a fetch fails or is blocked by policy, skip that source and continue.
- Cap your fetch attempts to the top 5 search results. If too few succeed, proceed with what you successfully fetched (or use search snippets) and note it in your summary. Do NOT retry endlessly.
"""

# ── Agent definition ──────────────────────────────────────────────────────────
# output_key='serp_findings' is the ONLY mechanism this agent uses to write
# to session.state. There are no direct state assignments anywhere in this file
# except inside _bootstrap_topic() which writes state['topic'] as a one-time
# bootstrap when it is missing. See the docstrings above for details.
serp_analyst_agent = LlmAgent(
    name="serp_analyst",
    model=_MODEL,
    instruction=_INSTRUCTION,
    # ── before_agent_callback ──────────────────────────────────────────────────
    # Runs BEFORE the instruction template is rendered against session.state.
    # Bootstraps state['topic'] from the user's chat message when trend_scout
    # hasn't set it yet (M1 only). Becomes a no-op in M5 when trend_scout runs
    # first. See _bootstrap_topic() docstring    # The M5 orchestrator pipeline passes state in this order:
    #   trend_scout writes: explicit_topic_request, topic
    #   serp_analyst reads: explicit_topic_request, topic
    #   serp_analyst writes: serp_findings
    #
    # That value is then available as {serp_findings} in the next agent's
    # instruction template (angle_finder, wired in M2).
    before_agent_callback=_bootstrap_topic,
    # ── output_key ─────────────────────────────────────────────────────────────
    # ADK automatically copies the agent's final text response into:
    #   session.state['serp_findings']
    # That value is then available as {serp_findings} in the next agent's
    # instruction template (angle_finder, wired in M2).
    output_key="serp_findings",
    # ── before_tool_callback ───────────────────────────────────────────────────
    # M4: intercepts the fetch tool BEFORE execution to enforce blocklist and fetch cap.
    before_tool_callback=fetch_before_policy_callback,
    # ── after_tool_callback ────────────────────────────────────────────────────
    # M4: intercepts the fetch tool AFTER execution to enforce semantic policies (ToU, PII).
    after_tool_callback=fetch_after_policy_callback,
    # ── tools ──────────────────────────────────────────────────────────────────
    # M3: MCP tools for real web research
    tools=[search_toolset, fetch_toolset],
    description=(
        "M4: researches a topic using MCP search+fetch tools, returns "
        "serp_findings JSON. Fetch calls are governed by policy callback."
    ),
)
