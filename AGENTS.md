# AGENTS.md
#
# Role: Project conventions and build commands for the Voice-Aware Content Engine.
# This file is automatically loaded by Antigravity (and compatible AI coding agents)
# to give them context before touching the codebase.
# Corresponds to Section 7 (repo structure) and Section 8 (safety rules) of specs/SPEC.md.

---

## Project overview

**Voice-Aware Content Engine** — a Google ADK multi-agent system that:
1. Learns a user's writing voice from a 1-minute audio clip (onboarding, once).
2. Proactively finds trending topics, researches the competitive landscape, and drafts
   on-brand articles — fully in the user's voice — with two human-in-the-loop approval gates.

Spec: `specs/SPEC.md` (source of truth). Code is disposable; the spec is the asset.

---

## Repository layout (Section 7)

```
content-engine/
├── specs/
│   ├── SPEC.md                 ← source of truth (never delete)
│   ├── scenarios.md            ← BDD Gherkin scenarios
│   └── evals/                  ← EDD JSON eval cases
├── .agent/skills/              ← optional rules-engine skill
├── agents/
│   ├── orchestrator.py         ← SequentialAgent wiring
│   ├── sub_agents/
│   │   ├── trend_scout.py
│   │   ├── serp_analyst.py
│   │   ├── angle_finder.py
│   │   ├── drafter.py
│   │   └── editor_guard.py
│   ├── onboarding/
│   │   └── voice_profile_builder.py
│   └── callbacks/
│       └── policy.py           ← security guardrail (after-tool callback)
├── config/
│   ├── allowlist.yaml          ← domains the fetch tool may scrape
│   └── mcp_servers.yaml        ← MCP connection config
├── knowledge_base/
│   └── notes.md                ← user's proprietary takes (read by angle_finder)
├── profile/
│   └── voice_profile.json      ← produced by onboarding (GITIGNORED)
├── .env.example                ← key NAMES only (no values)
├── .env                        ← real keys (GITIGNORED)
├── .gitignore
├── AGENTS.md                   ← this file
├── README.md
└── requirements.txt
```

---

## Build commands

```bash
# ── Environment setup ──────────────────────────────────────────────────────────
cp .env.example .env          # then fill in values
pip install -r requirements.txt

# ── ADK CLI (installed via uvx, not pip) ──────────────────────────────────────
uvx google-agents-cli setup   # one-time setup
agents-cli playground          # launch the dev UI (State tab for debugging)
agents-cli eval specs/evals/   # run EDD eval suite
agents-cli deploy              # deploy to Agent Engine

# ── MCP servers (started automatically by ADK via config/mcp_servers.yaml) ────
# search MCP:  npx -y tavily-mcp   (requires TAVILY_API_KEY in .env)
# fetch MCP:   uvx mcp-server-fetch (no API key needed)
```

---

## Coding conventions (enforce on every file you write)

### Secrets — HARD RULES (Section 8)
- **NEVER hardcode API keys, tokens, or passwords** in any source file, config, or test.
- **Always use `os.getenv("KEY_NAME")`** (or `python-dotenv` + `os.getenv`).
- `.env` is gitignored; `.env.example` has key NAMES only — zero values.
- Never pass credentials to public/community MCP servers.

### File-level comments
- Every Python file must start with a module docstring or block comment explaining:
  - what the file does
  - which Section of SPEC.md governs it
  - what session-state keys it reads and writes (for agents)

### Agent patterns
- Each sub-agent is an `LlmAgent` with exactly one `output_key`.
- `output_key` is the only way sub-agents write to `session.state` — no side-effects.
- The `SequentialAgent` in `orchestrator.py` is the only file that wires the pipeline order.
- Callbacks live in `agents/callbacks/` — keep execution logic separate from governance logic.

### MCP servers
- Connection config lives in `config/mcp_servers.yaml` — never inline command strings in agent code.
- The policy callback wraps the `fetch` tool — every fetched page is validated before use.

### Models to use (Section 6)
| Step | Model |
|------|-------|
| Reasoning (angle_finder, editor_guard) | `gemini-2.5-pro` |
| Fast / cheap (trend_scout, serp_analyst, drafter) | `gemini-2.5-flash` |
| Multimodal audio (voice_profile_builder) | `gemini-3.5-flash` |

### State schema
The shared session state "baton" is fully documented in Section 10 of `specs/SPEC.md`.
Do not add new state keys without updating the schema there first.

---

## Milestones (Section 15)

| Milestone | Goal | Test |
|-----------|------|------|
| M0 | Scaffold + secrets safe | `agents-cli playground` launches; no keys in files |
| M1 | `serp_analyst` skeleton with `output_key` | State tab shows `serp_findings` |
| M2 | Chain: `serp_analyst → angle_finder → drafter` | All 3 keys populate in order |
| M3 | Wire MCP servers | Startup logs list `search` + `fetch` tools |
| M4 | Policy callback + `editor_guard` | Non-allowlisted domain skipped; PII stripped |
| M5 | `trend_scout` + HITL gate 1 | Candidates appear; chosen topic flows to pipeline |
| M6 | `voice_profile_builder` onboarding | `voice_profile.json` created; drafts match voice |
| M7 | Eval, deploy, record | Eval suite green; endpoint live; README complete |

---

## Security checklist (run before every commit)

- [ ] `git grep -r "GOOGLE_API_KEY\s*=" agents/` returns nothing
- [ ] `git grep -r "TAVILY_API_KEY\s*=" agents/` returns nothing
- [ ] `profile/` is in `.gitignore` and not tracked
- [ ] `.env` is in `.gitignore` and not tracked
- [ ] All secrets accessed via `os.getenv()`
