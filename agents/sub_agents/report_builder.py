"""
agents/sub_agents/report_builder.py
-----------------------------------
Role: Assembles the Content Run Report (section 11.7) after editor_guard.
This is the business/accountability artifact. It calculates model cost, 
wall-clock time, and compares to a human baseline.

Governed by: specs/SPEC.md Section 11.7
"""

import datetime
import json
import logging
import os
import yaml
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions

logger = logging.getLogger(__name__)

# Load cost.yaml
_config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "cost.yaml",
)

class ReportBuilderAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. Load configuration
        cost_config = {}
        if os.path.exists(_config_path):
            with open(_config_path, "r", encoding="utf-8") as f:
                cost_config = yaml.safe_load(f) or {}
                
        human_baseline = cost_config.get("human_baseline", {"cost": 300, "time_label": "1 day"})
        models_config = cost_config.get("models", {})

        # 2. Extract State Variables
        angle_brief_raw = ctx.session.state.get("angle_brief", "{}")
        try:
            raw_stripped = angle_brief_raw.strip()
            if raw_stripped.startswith("```json"):
                raw_stripped = raw_stripped[7:-3]
            elif raw_stripped.startswith("```"):
                raw_stripped = raw_stripped[3:-3]
            angle_brief = json.loads(raw_stripped.strip())
        except Exception as e:
            logger.error(f"[report_builder] Failed to parse angle_brief JSON: {e}")
            angle_brief = {"angle": "Unknown", "why_new": "Unknown"}

        final_article = ctx.session.state.get("final_article", "No final article found.")
        serp_findings_raw = ctx.session.state.get("serp_findings", "{}")
        try:
            # Need to handle markdown block if present
            s_raw = serp_findings_raw.strip()
            if s_raw.startswith("```json"):
                s_raw = s_raw[7:-3]
            elif s_raw.startswith("```"):
                s_raw = s_raw[3:-3]
            serp_findings = json.loads(s_raw.strip())
        except Exception as e:
            logger.error(f"[report_builder] Failed to parse serp_findings JSON: {e}")
            serp_findings = {"sources": []}

        policy_notes = ctx.session.state.get("policy_notes", "No policy actions recorded.")
        voice_profile = ctx.session.state.get("voice_profile", {})

        # 3. Calculate Wall-clock Time & Token Usage
        events = ctx.session.events
        time_delta_str = "Unknown"
        if events:
            start_time = float(events[0].timestamp)
            end_time = float(events[-1].timestamp)
            delta_seconds = end_time - start_time
            minutes = int(delta_seconds // 60)
            seconds = int(delta_seconds % 60)
            if minutes > 0:
                time_delta_str = f"{minutes} min {seconds} sec"
            else:
                time_delta_str = f"{seconds} sec"

        total_cost = 0.0
        is_estimated = False
        fallback_used = False
        fallback_models = set()

        for ev in events:
            if ev.usage_metadata:
                # We have token usage
                p_tokens = ev.usage_metadata.prompt_token_count or 0
                c_tokens = ev.usage_metadata.candidates_token_count or 0
                
                # Default unknown model
                model_name = ev.model_version or "unknown-model"
                # Sometimes model_version has the provider prefix, e.g., 'models/gemini-2.5-flash'
                if "/" in model_name:
                    model_name = model_name.split("/")[-1]
                
                if model_name in models_config:
                    m_conf = models_config[model_name]
                    total_cost += (p_tokens / 1000.0) * m_conf.get("input_cost_per_1k", 0.0)
                    total_cost += (c_tokens / 1000.0) * m_conf.get("output_cost_per_1k", 0.0)
                    if m_conf.get("estimated", False):
                        is_estimated = True
                else:
                    # Model not in cost.yaml, fall back to something sensible or just log it
                    fallback_used = True
                    is_estimated = True
                    fallback_models.add(model_name)
                    # Let's use a very basic fallback estimate if not found (matching flash-ish pricing)
                    total_cost += (p_tokens / 1000.0) * 0.0001
                    total_cost += (c_tokens / 1000.0) * 0.0004

        if fallback_used:
            logger.warning(f"[report_builder] Models {fallback_models} not found in cost.yaml. Using fallback estimate.")

        cost_str = f"${total_cost:.4f}"
        if is_estimated or fallback_used:
            cost_str += " (estimated)"
            
        headline = f"~{cost_str} / ~{time_delta_str} vs ~${human_baseline.get('cost')} / {human_baseline.get('time_label')} (Human)"

        # 4. Render Markdown Report
        sources_list = "\\n".join([f"- {s.get('url')} : {s.get('summary')}" for s in serp_findings.get("sources", [])])
        
        report_md = f"""# Content Run Report

**ROI Panel**
> {headline}
"""
        if fallback_used:
            report_md += f"\n*Note: Costs for models {list(fallback_models)} are estimated because they were not found in cost.yaml.*\n"
            
        report_md += f"""
## 1. The Take
**Chosen Angle:** {angle_brief.get("angle")}
**Why New:** {angle_brief.get("why_new")}

## 2. Sources & Governance
**Sources Used:**
{sources_list if sources_list else "None explicitly listed."}

**Policy Trail:**
{policy_notes}

## 3. Voice Match
**Voice Applied:**
- Tone: {voice_profile.get("tone", "N/A")}
- Rhythm: {voice_profile.get("sentence_rhythm", "N/A")}
- Avoided: {", ".join(voice_profile.get("avoid", [])) if voice_profile.get("avoid") else "N/A"}

## 4. Final Article snippet
{final_article[:500]}...
"""

        # 5. Save to state and filesystem
        ctx.session.state["run_report"] = report_md
        
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "outputs")
        os.makedirs(out_dir, exist_ok=True)
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"run_report_{timestamp_str}.md")
        
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report_md)
            
        logger.info(f"[report_builder] Wrote run_report to {out_path}")

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"run_report": report_md})
        )


report_builder_agent = ReportBuilderAgent(
    name="report_builder",
    description="Assembles the Content Run Report and computes the ROI panel.",
)
