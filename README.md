# UniqVoice — a voice-aware content engine

> A Google ADK multi-agent system that learns your writing voice and produces
> on-brand, on-trend articles — with human-in-the-loop approval at every key decision.

---

## Problem

Most AI-generated marketing content is commodity content: everyone prompts the same
models with the same inputs and gets the same output. Separately, many AI marketing
initiatives struggle to show measurable ROI, because they automate *volume* instead of *judgment*.

## Solution

This engine automates the tedious 80% of content production (research, gap-finding,
drafting, compliance) while keeping the human in charge of the 20% that matters
(which angle, final approval) — and it writes in the user's *own voice*, learned
from a one-minute audio clip.

---

## Architecture

```
┌─────────────────────── Onboarding (run once) ──────────────────────────┐
│  Audio clip (+ optional answers) → voice_profile_builder → voice_profile.json │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────── Content Pipeline (SequentialAgent) ─────────────────┐
│                                                                         │
│  trend_scout ──► [HUMAN picks topic] ──► serp_analyst                  │
│                                               │                         │
│                                          angle_finder                   │
│                                               │                         │
│                                            drafter                      │
│                                               │                         │
│                                         editor_guard ──► report_builder │
│                                               │                         │
│                                        final_article.md                 │
└─────────────────────────────────────────────────────────────────────────┘

Tools: search MCP (tavily-mcp) · fetch MCP (mcp-server-fetch)
Guard: policy callback (allowlist + semantic ToU/PII check) on every fetch
```

*(See `specs/SPEC.md` Section 5 and `content_engine_architecture.html` for the full diagram.)*

---

## Live Web App

The project includes a FastAPI web application (`server.py`) that wraps the ADK
agent pipeline in a browser-based UI. The app is branded **UniqVoice** and provides
a three-step guided workflow:

### User Flow

| Step | Page | What happens |
|------|------|--------------|
| **1 · Voice** | `/` → `/voice-loading` → `/tone-captured` | User uploads an audio clip. The `voice_profile_builder` processes it and generates `profile/voice_profile.json`. The tone-captured page displays the resulting linguistic analysis (tone, rhythm, signature moves, negative constraints). |
| **2 · Angle** | `/angle` | User enters a topic. The frontend calls `/api/scout`, which runs `trend_scout` and returns topic candidates. The user picks one. The frontend then calls `/api/resume`, which streams the remaining pipeline (`serp_analyst → angle_finder → drafter → editor_guard → report_builder`) via NDJSON. A real-time sidebar shows agent progression, and a detailed log streams research/policy activity. |
| **3 · Create** | `/create` | Displays the finished output: the generated article, SERP common claims vs. the unique angle chosen, an ROI panel (production cost and time vs. a stated human baseline), and sources/references. The user can copy the article markdown to clipboard or download it as a `.md` file. |

### Running the Web App

```bash
# 1. Make sure .env is configured (see "Configure secrets" below)
# 2. Start the server
uv run uvicorn server:app --reload --port 8001

# 3. Open in browser
open http://127.0.0.1:8001
```

The `--reload` flag watches for file changes and auto-restarts. On first launch,
the MCP servers (`tavily-mcp` and `mcp-server-fetch`) are started automatically
via `config/mcp_servers.yaml`. You should see two `✅ MCP handshake successful`
lines in the terminal confirming they connected.

### API Endpoints

| Method | Path | Request Body | What it does |
|--------|------|-------------|--------------|
| `POST` | `/api/voice-upload` | `multipart/form-data` with `audio` file | Runs `voice_profile_builder` on the uploaded audio clip. Returns the generated voice profile JSON, or an error. |
| `POST` | `/api/scout` | `{ "topic": "..." }` | Kicks off the pipeline. Runs `trend_scout`, which calls the `request_input` function to present topic candidates. Returns `{ run_id, topic_candidates, topic }`. The `run_id` is needed to resume the pipeline. |
| `POST` | `/api/resume` | `{ "run_id": "...", "chosen_index": 0 }` | Resumes the pipeline after the user picks a topic candidate. Returns a **streaming NDJSON response** with events: `tool_call` (search/fetch activity), `text` (policy log lines), `agent_complete` (sidebar progression), and a final `complete` object containing all session state (`final_article`, `serp_findings`, `angle_brief`, `run_report`, `cost_metrics`, etc.). |
| `POST` | `/api/run` | `{ "topic": "..." }` | Runs the entire pipeline without human-in-the-loop — auto-selects the first topic candidate. Returns the full session state as JSON. Used by the Create page when loading from `localStorage` isn't possible. |

### Page Routes

| Path | File served |
|------|-------------|
| `/` | `web/index.html` — Voice upload / onboarding |
| `/voice-loading` | `web/voice_loading.html` — Processing animation |
| `/tone-captured` | `web/tone_captured.html` — Voice profile results |
| `/angle` | `web/angle.html` — Topic scouting + candidate selection |
| `/process-alignment` | `web/process_alignment.html` — Real-time pipeline execution view (loaded as an overlay by `/angle`) |
| `/create` | `web/create.html` — Final article + ROI report |

Static assets (CSS, images) are served from `web/static/`.

---

## Quick Start (CLI only)

If you want to use the ADK CLI playground instead of the web app:

### Prerequisites

- Python ≥ 3.11
- Node.js ≥ 18 (for `npx tavily-mcp`)
- [`uv`](https://docs.astral.sh/uv/) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### 1 · Clone and install

```bash
git clone <repo-url>
cd UniqVoice
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

---

## Eval suite

```bash
uv run pytest tests/
```

The suite was originally authored for `agents-cli eval`, but the Vertex-backed eval
SDK can't introspect ADK `MCPToolset` objects, so it runs on an ADK-native
`InMemoryRunner` harness instead.

Six eval cases pass, including two regression tests for bugs found and fixed during the build:
- `serp_reads_top_pages` — SERP analyst reads ≥ 2 sources and extracts `common_claims`
- `guard_strips_pii` — editor guard removes an email and logs it to `policy_notes`
- `angle_is_non_commodity` — angle finder contradicts / extends `common_claims`
- `subject_anchored` (regression) — an explicit subject survives candidate selection through the final article
- `security_blocks_no_loop` (regression) — fetch cap respected, run completes without looping, blocks logged
- `voice_applied` — the draft honours the loaded voice profile

---

## Deployment

```bash
agents-cli deploy   # architected for Agent Engine; not deployed for judging
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
