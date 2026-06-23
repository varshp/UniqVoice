# README.md
#
# Role: Project overview, setup instructions, and architecture summary.
# Fill in the architecture diagram and deployment steps as you complete milestones.
# See specs/SPEC.md Section 16 for deployment reproducibility requirements.

# Voice-Aware Content Engine

> A Google ADK multi-agent system that learns your writing voice and produces
> on-brand, on-trend articles — with human-in-the-loop approval at every key decision.

---

## Problem

Most AI-generated marketing content is commodity content: everyone prompts the same
models with the same inputs and gets the same output. Separately, ~95% of AI marketing
initiatives show no measurable ROI because they automate *volume* instead of *judgment*.

## Solution

This engine automates the tedious 80% of content production (research, gap-finding,
drafting, compliance) while keeping the human in charge of the 20% that matters
(which angle, final approval) — and it writes in the user's *own voice*, learned
from a one-minute audio clip.

---

## Architecture

```
┌─────────────────────── Onboarding (run once) ──────────────────────────┐
│  Audio clip + 3 answers → voice_profile_builder → voice_profile.json   │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────── Content Pipeline (SequentialAgent) ─────────────────┐
│                                                                         │
│  trend_scout ──► [HUMAN picks topic] ──► serp_analyst                  │
│                                               │                         │
│                                          angle_finder                   │
│                                               │                         │
│                                            drafter                      │
│                                               │                         │
│                                         editor_guard ──► [HUMAN OK?]   │
│                                               │                         │
│                                        final_article.md                 │
└─────────────────────────────────────────────────────────────────────────┘

Tools: search MCP (tavily-mcp) · fetch MCP (mcp-server-fetch)
Guard: policy callback (allowlist + semantic ToU/PII check) on every fetch
```

*(See `specs/SPEC.md` Section 5 and `content_engine_architecture.html` for the full diagram.)*

---

## Quick start

### Prerequisites

- Python ≥ 3.11
- Node.js ≥ 18 (for `npx tavily-mcp`)
- [`uv`](https://docs.astral.sh/uv/) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### 1 · Clone and install

```bash
git clone <repo-url>
cd content-engine
pip install -r requirements.txt
uvx google-agents-cli setup   # one-time ADK CLI setup
```

### 2 · Configure secrets

```bash
cp .env.example .env
# Edit .env and fill in:
#   GOOGLE_API_KEY   — https://aistudio.google.com/app/apikey
#   TAVILY_API_KEY   — https://tavily.com  (free tier)
```

### 3 · Run the dev UI

```bash
agents-cli playground
```

Open the URL shown in the terminal. Use the **State tab** to inspect session state
after each agent step.

### 4 · Run the onboarding (once per user)

```bash
# TODO: fill in after M6
python -m agents.onboarding.voice_profile_builder --audio path/to/clip.m4a
```

### 5 · Run the full pipeline

```bash
# TODO: fill in after M5
agents-cli run
```

---

## Eval suite

```bash
agents-cli eval specs/evals/
```

Three EDD eval cases (see `specs/evals/`):
- `serp_reads_top_pages_001` — SERP analyst reads ≥ 2 sources and extracts `common_claims`
- `guard_strips_pii_001` — editor guard removes an email and logs it to `policy_notes`
- `angle_is_non_commodity_001` — angle finder contradicts / extends `common_claims`

---

## Deployment

```bash
agents-cli deploy   # deploys to Agent Engine
```

<!-- TODO (M7): add the deployed endpoint URL and any environment variables
     required on the Agent Engine side. -->

---

## Repository structure

See `AGENTS.md` for the full annotated tree and coding conventions.

---

## Roadmap (Phase 2)

- Internal/external link insertion with live 404 validation
- Transcript ingestion for proprietary knowledge input
- Real Google Trends API integration (once GA)
- Live conversational voice onboarding (mic + TTS frontend)
- Multi-topic batch runs via `LoopAgent`
- Observability dashboard

---

## Spec

The single source of truth for this project is `specs/SPEC.md`. Code is disposable;
the spec is the asset.
