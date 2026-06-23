"""
agents/agent.py
---------------
Role: ADK entry-point module for the content pipeline.
      `adk web` (launched by `agents-cli playground`) discovers the agent by
      importing this module and reading its `root_agent` and `app` exports.

      This file is the bridge between the agents-cli project structure and our
      pipeline code. It simply re-exports the SequentialAgent from orchestrator.py.

Governed by: specs/SPEC.md Section 5 (System Architecture) and Section 7 (Repo Layout).

Session state written by this pipeline (Section 10 "baton"):
  → topic_candidates  (trend_scout)
  → topic             (human HITL gate 1)
  → serp_findings     (serp_analyst)
  → angle_brief       (angle_finder)
  → draft             (drafter)
  → final_article     (editor_guard)
  → policy_notes      (editor_guard + policy callback)

Secrets: loaded from agents/.env via python-dotenv; never hardcoded here.
"""

import os

from dotenv import load_dotenv
from google.adk.apps import App

# Load secrets from agents/.env (or the root .env) before importing any agent
# that calls os.getenv(). This ensures all environment variables are available
# when sub-agents initialise their model clients.
# Note: dotenv does NOT overwrite variables already set in the environment.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)

# Import the SequentialAgent defined in orchestrator.py.
# During M0 (scaffold) the sub-agents are stubs — the pipeline runs but
# produces placeholder output until each milestone adds real logic.
from agents.orchestrator import root_agent  # noqa: E402

# App wraps the root_agent for the ADK web UI and playground.
# The `name` here must match the agent_directory in agents-cli-manifest.yaml.
app = App(
    root_agent=root_agent,
    name="agents",
)
