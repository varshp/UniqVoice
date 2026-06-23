# SPEC — Voice-Aware Content Engine

> **What this document is.** The single source of truth for building this agent. It follows the
> Day 5 spec-driven pattern (Markdown narrative + YAML schemas + BDD scenarios + EDD eval cases).
> Keep it in `specs/SPEC.md`. At each build step you tell your coding agent *"Read the relevant
> section of `specs/SPEC.md` and implement it,"* then you test, then you move on. Code is
> disposable; **this spec is the asset.**

---

## 1. Background — the "why" behind the "what"

Most published marketing content is commodity content: everyone reads the same top-ranking
articles and rewrites them, so nothing new enters the conversation. Separately, ~95% of AI
marketing initiatives show no measurable ROI, often because they automate *volume* instead of
*judgment*. This project automates the tedious 80% of content production (research, gap-finding,
drafting, link-building, compliance) while keeping the human in charge of the 20% that matters
(which angle, and final approval) — and it writes in the user's *own voice*, learned from a
one-minute voice sample.

**Why agents (not one prompt):** the job is genuinely multi-step and each step needs a different
skill and a different tool. A single prompt would have to search, analyse, reason about a
knowledge base, write, and self-police all at once — which is exactly where quality collapses.
Splitting it into specialised agents that pass a shared notebook down the line keeps each step
sharp, debuggable, and individually testable. This is the ADK "reduction of search space"
principle: fewer tools per agent → fewer wrong moves.

**Why "proactive":** the engine *finds its own topic* from trend signals instead of waiting for the
user to supply one. Trigger-driven beats query-driven for a content team that needs to ride timing.

---

## 2. Goals and non-goals

### In scope (the MVP you will build)
- A run-once **onboarding** that learns the user's voice + topics from a 1-minute audio clip.
- A per-article **sequential pipeline**: find topic → analyse competition → find a non-commodity
  angle → draft in the user's voice → guard the output.
- **Two human-in-the-loop gates**: pick the angle; approve the final.
- A **security policy layer** — a semantic-first guard (ToU/PII check + hard fetch cap) that blocks
  disallowed/unsafe content and strips PII, plus two human-in-the-loop gates.
- **Two MCP servers** (web search + page fetch).
- A **Content Run Report** per run (the take + governance trail + voice match + cost/time ROI).
- An **ADK-native eval suite** (`pytest` + `InMemoryRunner`).
- *(Optional)* **Deployment** to Agent Engine via `agents-cli` — documented, not required for judging.

### Out of scope (roadmap — name these in the writeup, do not build now)
- Internal/external link insertion with live 404-checking.
- Transcript ingestion for proprietary input.
- Real Google Trends API (alpha/limited access) — use an LLM trend-scout instead.
- Live two-way voice conversation (needs a frontend with mic + TTS).
- Multi-topic batch generation (LoopAgent over several topics).

---

## 3. Track and rubric mapping (keep this visible while building)

**Track:** Agents for Business.

| Course concept | Where it lives in this build | Graded in |
|---|---|---|
| Multi-agent system (ADK) | `SequentialAgent` orchestrator + 6 pipeline sub-agents + 1 onboarding agent | Code |
| MCP server | `search` (Tavily) + `fetch` MCP servers wired as agent tools | Code |
| Security features | `policy.py` semantic-first guard (ToU/PII check + hard fetch cap) + output PII strip + HITL gates | Code + Video |
| Agent skills (Agents CLI / eval) | `agents-cli` setup/playground; ADK-native eval suite (`InMemoryRunner` + pytest) | Code |
| Deployability *(optional)* | Dockerfile + documented `agents-cli deploy` path (not deployed — Vertex friction; not required for judging) | Video |
| Antigravity *(optional)* | built the project inside Antigravity; show the IDE/sandbox on camera | Video |
| Multimodal voice onboarding *(value-add)* | `voice_profile_builder` learns voice from a 1-min audio clip | Code + Video |

You need 3. This build banks 4 solidly (ADK, MCP, security, Agents-CLI/eval), with the voice
differentiator on top — comfortably past the bar.

---

## 4. Users and the user journey

**Persona:** a marketer / founder who publishes regularly and wants on-brand, timely content
without doing the grind.

**Journey (the human makes exactly two decisions):**
1. *(once)* Records a 1-minute clip answering three prompts; the engine builds a voice profile.
2. Triggers a run. `trend_scout` returns 2–3 candidate angles. **→ user picks one.** (gate 1)
3. The pipeline researches, finds the gap, and drafts in the user's voice. The user sees a short
   progress trail.
4. The guard runs; any blocked source or stripped PII is surfaced as an honesty note.
5. User reviews the finished draft. **→ user approves before any deliver/publish action.** (gate 2)
6. Output is delivered as clean Markdown.

This journey *is* the 5-minute demo script; steps 2→5 are the live demo, step 4 is the security beat.

---

## 5. System architecture

Two flows, both built on ADK. See `content_engine_architecture.html` for the diagram.

**Onboarding flow (run once):**
`Audio clip + 3 answers` → `voice_profile_builder` (Gemini multimodal) → writes
`voice_profile`, `tone_notes`, `topic_seeds` to a persisted profile store.

**Content pipeline (`SequentialAgent`, run per article):**
`trend_scout` → `serp_analyst` → `angle_finder` → `drafter` → `editor_guard` → `report_builder`.
Each sub-agent reads only the state keys it needs and writes exactly one new key via `output_key`.
(The final `report_builder` only reads — it assembles the Content Run Report from existing state;
see section 11.7.)
Coordination is **shared session state** (ADK's mechanism for simple in-pipeline hand-off);
tools reach the outside world via **MCP**; a **callback** on the fetch tool enforces policy.

---

## 6. Tech stack (with versions — pin these in `requirements.txt`)

```yaml
runtime:
  python: ">=3.11"
core:
  google-adk: latest            # Agent Development Kit (SequentialAgent, LlmAgent, callbacks)
  google-agents-cli: latest     # installed via: uvx google-agents-cli setup
  mcp: latest                   # Model Context Protocol Python SDK
  python-dotenv: latest         # load .env
models:
  # Actual runtime assignments (Gemini 3.x — confirmed current at build time):
  voice_profile_builder: "gemini-3.5-flash"   # multimodal, ingests audio natively
  trend_scout:           "gemini-3.1-flash-lite"
  serp_analyst:          "gemini-3-flash"
  angle_finder:          "gemini-3.5-flash"
  drafter:               "gemini-3.5-flash"
  editor_guard:          "gemini-3.5-flash"
  policy_semantic_check: "gemini-3.5-flash"    # / flash-lite
  note: "All active agents run on Flash tiers (3.1-pro is paid-only with no free quota; 3.5-flash
         beats 3.1-pro on these agent tasks). Confirm current Gemini model IDs before pinning."
mcp_servers:
  search: "tavily-mcp"          # npx -y tavily-mcp  (free tier ~1000/mo). Alt: Brave Search MCP, Exa MCP
  fetch: "mcp-server-fetch"     # uvx mcp-server-fetch  (no API key; converts pages to markdown)
build_env:
  ide: "Antigravity"            # optional but banks the Antigravity concept; show on camera
```

---

## 7. Repository structure

```
content-engine/
├── specs/
│   ├── SPEC.md                 # this file (source of truth)
│   ├── scenarios.md            # BDD Gherkin scenarios (section 12)
│   └── evals/                  # EDD JSON eval cases (section 13)
├── .agent/skills/              # OPTIONAL: rules-engine skill (Antigravity-recognised)
├── agents/
│   ├── orchestrator.py         # SequentialAgent wiring the pipeline
│   ├── sub_agents/
│   │   ├── trend_scout.py
│   │   ├── serp_analyst.py
│   │   ├── angle_finder.py
│   │   ├── drafter.py
│   │   ├── editor_guard.py
│   │   └── report_builder.py    # assembles the Content Run Report (section 11.7)
│   ├── onboarding/
│   │   └── voice_profile_builder.py
│   └── callbacks/
│       └── policy.py           # the security guardrail
├── config/
│   ├── allowlist.yaml          # domains the fetch tool may scrape
│   ├── cost.yaml               # per-model $/1k tokens + human baseline (section 11.7)
│   └── mcp_servers.yaml        # MCP connection config
├── outputs/                    # generated run reports: run_report_<timestamp>.md
├── knowledge_base/
│   └── notes.md                # the user's proprietary takes / positioning (read by angle_finder)
├── profile/
│   └── voice_profile.json      # produced by onboarding  (GITIGNORED)
├── .env.example                # names of required keys, NO values
├── .env                        # real keys  (GITIGNORED)
├── .gitignore
├── AGENTS.md                   # project conventions + build commands (always loaded by the agent)
├── README.md                   # problem, solution, architecture, setup, diagram
└── requirements.txt
```

---

## 8. Environment, secrets and safety rules (read before writing any code)

```yaml
secrets:
  file: ".env"                  # never committed
  gitignore_must_include: [".env", "profile/", "*.mp3", "*.wav", "*.m4a", "__pycache__/"]
  keys:
    GOOGLE_API_KEY: "for Gemini models via ADK"
    TAVILY_API_KEY: "for the search MCP server"
hard_rules:
  - "NO API keys, tokens, or passwords anywhere in code or in the spec. Use os.getenv()."
  - "Provide .env.example with key NAMES only — never values."
  - "Never pass credentials to public/community MCP servers."
  - "Do not retain raw audio after the voice profile is extracted (privacy)."
  - "Every fetched page passes the policy callback before its content is used."
```

> Tell your coding agent this explicitly at setup so keys never get hardcoded. This protects the
> 🚨 'no keys in code' rubric rule, which is an easy accidental fail.

---

## 9. MCP servers to connect

The vibe-coder approach: **consume** pre-built servers, don't write your own. For each server the
flow is the Day 2 three-step: **Discovery → Configuration → Connection (handshake to list tools).**

### 9.1 Search MCP (`tavily-mcp`)
- **Discovery:** public server, runnable via `npx -y tavily-mcp`. Sign up at tavily.com for a free key.
- **Configuration:** put `TAVILY_API_KEY` in `.env`; reference the server in `config/mcp_servers.yaml`
  with read-only scope. Pass the key via env var, never inline.
- **Connection / verify:** on first run, list tools and confirm a `search` tool appears with a valid
  schema. Used by `trend_scout` (find trends) and `serp_analyst` (find top-ranking pieces).

### 9.2 Fetch MCP (`mcp-server-fetch`)
- **Discovery:** official MCP server, runnable via `uvx mcp-server-fetch`. No API key.
- **Configuration:** register in `config/mcp_servers.yaml`. Its job is to fetch a URL and return
  clean markdown.
- **Connection / verify:** list tools, confirm a `fetch` tool. **Every call is wrapped by the policy
  callback** (section 11). Used by `serp_analyst` to read the top pages.

```yaml
# config/mcp_servers.yaml  (illustrative shape — your coding agent fills exact syntax for ADK MCPToolset)
servers:
  - name: search
    transport: stdio
    command: "npx"
    args: ["-y", "tavily-mcp"]
    env: ["TAVILY_API_KEY"]
    scope: read-only
  - name: fetch
    transport: stdio
    command: "uvx"
    args: ["mcp-server-fetch"]
    scope: read-only
    wrap_with: policy_callback   # enforce allowlist + ToU/PII before content is used
```

**Phase-2 servers (do not connect now):** SerpApi MCP (real Trends), Google Drive MCP (KB/deliver),
Gmail MCP (email the draft, gated), filesystem MCP (sitemap/local files).

---

## 10. Shared state schema (the "baton")

```yaml
# session.state keys, in the order they are written
onboarding:
  voice_profile:   # object: how the user writes
    tone: string                 # e.g. "direct, warm, slightly contrarian"
    sentence_rhythm: string      # e.g. "short punchy openers, longer middles"
    vocabulary: [string]         # signature words/phrases
    rhetorical_moves: [string]   # e.g. "opens with a stat, ends with a challenge"
    avoid: [string]              # clichés / words the user never uses
  tone_notes: string             # free-text summary for the drafter prompt
  topic_seeds: [string]          # the lanes the user wants to write in

pipeline:
  explicit_topic_request: string # the user's typed SUBJECT — persists through the whole pipeline; takes precedence over topic_seeds
  topic: string                  # chosen by the human from trend_scout candidates (must retain the subject)
  topic_candidates: [string]     # what trend_scout proposed (each retains the subject; kept for the writeup/demo)
  serp_findings:                 # what the top-ranking pieces say
    sources: [{url: string, summary: string}]
    common_claims: [string]      # the "commodity" consensus to differentiate against
  angle_brief:                   # the non-commodity plan
    angle: string
    why_new: string              # how it differs from common_claims
    outline: [string]
    must_include: [string]       # substance/style requirements (e.g. a concrete example, a clear takeaway) — NOT forced product mentions
  draft: string                  # full draft, written in voice_profile
  final_article: string          # post slop-clean + policy
  policy_notes: [string]         # human-readable notes on anything blocked/stripped
  run_report: string             # markdown accountability artifact (see section 11.7); also saved to outputs/
```

---

## 11. Component specifications

For each agent: its job, model, what it reads, what it writes (`output_key`), its tools, and the
**intent** of its instruction (your coding agent writes the actual prompt; you refine it).

### 11.1 `voice_profile_builder` (onboarding, run once)
- **Model:** Gemini multimodal (accepts the audio file directly — no separate speech-to-text).
- **Reads:** an audio file path + the user's 3 text/voice answers.
- **Writes:** `voice_profile`, `tone_notes`, `topic_seeds` → persisted to `profile/voice_profile.json`.
- **Tools:** none (model ingests audio natively).
- **Instruction intent:** "Analyse this 1-minute clip and these answers. Extract HOW this person
  communicates — tone, rhythm, signature vocabulary, rhetorical patterns, what they avoid — and the
  topics they care about. Output the `voice_profile` schema. Then discard the raw audio."
- **Edge cases:** clip < 20s or missing → ask the user to re-record; never fabricate a profile.

### 11.2 `trend_scout`
- **Model:** Gemini flash. **Tool:** `search` (MCP).
- **Reads:** `explicit_topic_request` (if the user typed a topic) else `topic_seeds`.
  **Writes:** `topic_candidates`, and `topic` (after human picks).
- **Instruction intent:** "If the user gave an explicit topic, treat it as the SUBJECT and propose
  2–3 specific *angles on that subject* — every candidate must retain the subject. Only if no topic
  was given, suggest angles from `topic_seeds`. Return candidates for the human to choose."
  HITL: surface candidates; the run continues with the chosen `topic` (which still contains the subject).
- **Critical:** an explicitly typed topic ALWAYS wins over profile `topic_seeds`, and the SUBJECT
  must never be dropped from a candidate (a subtle bug we hit: the chosen angle lost "SpaceX" and the
  whole pipeline went generic). Keep `explicit_topic_request` in state so downstream agents can anchor to it.
- **Edge case:** no fresh signal → fall back to evergreen angles from `topic_seeds`, flagged as such.

### 11.3 `serp_analyst`
- **Model:** Gemini flash. **Tools:** `search` + `fetch` (MCP).
- **Reads:** `topic`, `explicit_topic_request`. **Writes:** `serp_findings`.
- **Instruction intent:** "Find the current top-ranking pieces for this topic, read them, and
  summarise what they collectively say. Anchor the search to the SUBJECT (`explicit_topic_request`)
  plus the chosen angle so research stays on-subject. Extract the `common_claims` — the consensus
  take — so a later agent can deliberately go beyond it." Respects the policy callback on every fetch.

### 11.4 `angle_finder`
- **Model:** Gemini pro (this is the reasoning step). **Tools:** none (reasons over state + KB file).
- **Reads:** `serp_findings`, `explicit_topic_request`/`topic_seeds`. **Writes:** `angle_brief`.
- **Instruction intent:** "Given the commodity consensus, find an angle that adds something NEW —
  reframes or contradicts the `common_claims`, not restates them. Produce `angle`, `why_new`, an
  `outline`, and `must_include` (a concrete example + a clear takeaway). Keep the SUBJECT central."
  This is the differentiator vs generic AI content. (Note: no forced product mentions — the output
  is editorial; forcing product/vocabulary terms produces exactly the slop we avoid.)

### 11.5 `drafter`
- **Model:** Gemini flash. **Tools:** none.
- **Reads:** `angle_brief`, `voice_profile`, `tone_notes`. **Writes:** `draft`.
- **Instruction intent:** "Write the article to the outline AND in this exact voice — match the tone,
  rhythm, vocabulary, and rhetorical moves; avoid the listed clichés. Cover every `must_include`."

### 11.6 `editor_guard` (the security step)
- **Model:** Gemini pro. **Tool:** none directly; hosts the policy logic + a final scan.
- **Reads:** `draft`. **Writes:** `final_article`, `policy_notes`.
- **Instruction intent:** "Slop-clean: remove filler, hedging, and AI tells. Then scan for PII
  (emails, phone numbers, private URLs) and remove it. Record what you changed in `policy_notes`."
  HITL: the human approves `final_article` before any deliver/publish action.

### 11.7 `report_builder` (the Content Run Report — business/accountability artifact)
- **Model:** Gemini flash (light assembly only — or pure code; no reasoning needed).
- **Reads:** `angle_brief`, `final_article`, `serp_findings`, `policy_notes`, `voice_profile`.
- **Writes:** `run_report` (markdown) → also saved to `outputs/run_report_<timestamp>.md`.
- **Tools:** none. Runs LAST, after `editor_guard`. **Creates nothing new — it surfaces what the
  pipeline already did**, packaged as a one-page accountability artifact a stakeholder can read.
- **Instruction intent / sections of the report:**
  1. **The take** — the chosen `angle` + `why_new` (why this is non-commodity, not the consensus).
  2. **Sources & governance** — the `serp_findings` sources used, plus the full `policy_notes` trail
     (blocked / snippet-only / ToU / PII stripped / fetch-cap hit). This is the audit log.
  3. **Voice match** — confirmation the draft was written against the loaded `voice_profile`
     (tone / rhythm / avoid-list honoured).
  4. **ROI panel** — estimated **model cost** and **wall-clock time** for this run, vs a configurable
     **human baseline** (default `$300`, `1 day` for an equivalent agency draft). Headline the delta
     (e.g. `~$0.15 / ~4 min  vs  ~$300 / 1 day`).
- **Cost rule (keep it honest):** compute cost from real token usage if the response exposes it;
  otherwise fall back to a per-run estimate from `config/cost.yaml` (per-model input/output $/1k
  tokens). **Label every estimate as an estimate; never invent token counts or inflate the delta.**
- **Why this matters (Business track):** this is the artifact that puts *cost/revenue on the line* —
  it reframes the system from "AI that writes" to "an accountable, governed, costed content run."
  It is the primary on-camera demo asset.

---

## 12. Security and guardrails (the policy callback)

Implemented in `agents/callbacks/policy.py` on the `fetch` tool. **Design note — this evolved during
the build:** it started as a strict structural *allowlist gate* (only allowlisted domains could be
fetched). That **starved non-marketing topics** — a finance query returned finance sources that
weren't on a marketing allowlist, so every source was blocked and the agent looped retrying. It was
redesigned into a **semantic-first guard** that is general-purpose and still demonstrably blocks.
This evolution is a key writeup beat (engineering judgment under a real failure).

```yaml
policy_callback:
  model: "before + after tool callbacks on the fetch tool"
  before_fetch:
    blocklist_check:
      rule: "Is the domain in config/blocklist.yaml (known content-farm/spam/unsafe)?"
      on_match: "skip the fetch entirely; append policy_notes: 'blocked {domain}: blocklist'"
    fetch_cap:
      rule: "Hard cap on fetch attempts per run, enforced in CODE (not just the prompt)"
      limit: 5
      on_exceed: "skip further fetches; append 'skipped: fetch cap reached' — guarantees no loop"
  after_fetch:
    semantic_check:                       # the PRIMARY guard — general-purpose, content-aware
      rule: "Ask Gemini Flash: does using this content violate ToU, or does it contain PII?"
      on_fail: "drop content; append 'blocked {domain}: ToU/PII'"
      on_pass: "append 'fetched (ok)'"
  allowlist_role:
    file: "config/allowlist.yaml"
    use: "SOFT ranking preference only (curated reputable domains the agent should prefer) —
           NOT a hard gate. Non-listed domains are allowed unless blocklisted/flagged."
  separation_of_concerns: "execution logic (agents) stays separate from governance logic (callback)"
output_guard:
  where: "editor_guard"
  rule: "final PII scan on the draft; strip emails/phones/private URLs; log to policy_notes"
hitl_gates:
  - "human selects topic from trend_scout candidates"
  - "human approves final_article before deliver/publish"
```

> **Trust-tiering option (if implemented):** allowlisted domains get a deep `fetch`; non-allowlisted
> domains contribute via their search snippet only (still ToU/PII-checked). `policy_notes` then logs
> three states — `deep-fetched (trusted)`, `snippet-only (untrusted)`, `blocked (ToU/PII)`.

---

## 13. BDD scenarios (store in `specs/scenarios.md`)

Gherkin keeps the agent on rails. Include the happy path **and** edge cases.

```gherkin
Feature: Voice-aware content generation

  Scenario: Produce an on-brand article from a chosen trend
    Given a saved voice_profile and topic_seeds
    When the user triggers a run and selects a topic from the candidates
    Then serp_findings, angle_brief, draft and final_article are produced in order
    And final_article reflects the voice_profile tone and includes every must_include item

  Scenario: No fresh trend is available
    Given topic_seeds exist but search returns nothing timely
    When trend_scout runs
    Then it proposes evergreen angles from topic_seeds
    And it flags them as evergreen rather than trending

  Scenario: A source is blocked by terms of use
    Given the fetch tool returns content from a non-allowlisted domain
    When the policy callback runs
    Then the content is dropped
    And policy_notes records the skipped source
    And the pipeline continues without it

  Scenario: PII appears in the draft
    Given a draft containing an email address
    When editor_guard runs
    Then the email is removed from final_article
    And policy_notes records that PII was stripped

  Scenario: Voice clip is too short
    Given an uploaded clip shorter than 20 seconds
    When voice_profile_builder runs
    Then it asks the user to re-record
    And it does not fabricate a voice_profile
```

---

## 14. Evaluation cases (EDD)

Per the course: define Input / Expected tools / Expected output up front to surface ambiguity early.
The first three were written before the code (EDD); the last two are regression tests for bugs found
and fixed during the build (subject anchoring, security/no-loop).

**How they run:** originally targeted `agents-cli eval` (Vertex-backed), but the Vertex evals SDK
can't introspect ADK `McpToolset` (`'McpToolset is not a callable object'`). Switched to **ADK-native
eval** — `pytest` + ADK `InMemoryRunner`, which runs the real agent (MCP and all). Deterministic
rubrics are concrete checks; qualitative ones use an LLM-as-judge. State is seeded via
`create_session(state=...)`; HITL turns are replayed through `run_async`. **Run with:** `uv run pytest tests/`.

```json
[
  {
    "case_id": "serp_reads_top_pages_001",
    "input": "topic = 'why AI marketing pilots stall'",
    "expected_agent": "serp_analyst",
    "expected_tool_calls": [{"tool": "tavily_search", "args": {"query_contains": "AI marketing pilots"}}],
    "expected_output_format": "serp_findings with sources and common_claims populated",
    "rubric": ["serp_findings.sources length >= 2", "common_claims is non-empty"]
  },
  {
    "case_id": "guard_strips_pii_001",
    "input": "draft contains 'reach me at jane@acme.com'",
    "expected_agent": "editor_guard",
    "expected_tool_calls": [],
    "expected_output_format": "final_article with no email; policy_notes mentions PII removed",
    "rubric": ["no email in final_article (regex)", "meaning preserved", "logged in policy_notes"]
  },
  {
    "case_id": "angle_is_non_commodity_001",
    "input": "serp_findings.common_claims = ['use AI to write more posts faster']",
    "expected_agent": "angle_finder",
    "expected_tool_calls": [],
    "expected_output_format": "angle_brief where why_new reframes/contradicts the common claim",
    "rubric": ["why_new reframes/contradicts common_claims (not a restatement)", "outline has >= 4 beats"]
  },
  {
    "case_id": "subject_anchored_001",
    "input": "explicit_topic_request = 'is it a mistake to invest in SpaceX post-IPO'",
    "expected_agent": "pipeline (end-to-end)",
    "expected_tool_calls": [],
    "expected_output_format": "subject 'SpaceX' preserved from candidates through final_article",
    "rubric": ["every topic_candidate contains 'SpaceX'", "final_article mentions SpaceX and (Starship or Starlink)", "not generic IPO advice"]
  },
  {
    "case_id": "security_blocks_no_loop_001",
    "input": "explicit_topic_request = 'is it a mistake to invest in SpaceX post-IPO'",
    "expected_agent": "pipeline (end-to-end)",
    "expected_tool_calls": [],
    "expected_output_format": "policy_notes audit log present; run completes without looping",
    "rubric": ["fetch_attempt_count <= 5", "final_article is produced (no loop)", "if a ToU/blocklisted source appears, policy_notes logs 'blocked' (conditional)"]
  },
  {
    "case_id": "voice_applied_001",
    "input": "voice_profile loaded; topic = 'why AI marketing pilots stall'",
    "expected_agent": "drafter",
    "expected_tool_calls": [],
    "expected_output_format": "final_article reflects the loaded voice_profile",
    "rubric": ["none of the avoid-list phrases present", "opens with a narrative (LLM-judge)", "ends on a revelation-style close"]
  }
]
```

---

## 15. Build milestones — the paste-and-test loop

Each milestone = one focused sitting. **Paste the prompt into your coding agent, run the test, confirm
"done when," move on.** Always keep `specs/SPEC.md` in the repo so the agent can read it.

### M0 — Environment + scaffold  *(setup is the biggest time sink — budget for it)*
- **Goal:** working ADK project, secrets safe, agent can run an empty pipeline.
- **Paste:**
  > "Set up a Google ADK project for the spec in `specs/SPEC.md`. Run `uvx google-agents-cli setup`.
  > Create the folder structure from section 7, a `requirements.txt` pinned to section 6, an
  > `.env.example` with key NAMES only (no values), a `.gitignore` per section 8, an `AGENTS.md` with
  > our conventions and build commands, and a `README.md` stub. Use `os.getenv()` for all secrets —
  > never hardcode keys. Add a code comment on every file explaining its role."
- **Test:** `agents-cli playground` launches; `.env` is gitignored; no keys in any file.
- **Done when:** the empty project runs and the repo tree matches section 7.

### M1 — Skeleton: one agent end-to-end
- **Goal:** prove the `SequentialAgent` + `output_key` + `session.state` mechanic.
- **Paste:**
  > "Implement only `serp_analyst` as an `LlmAgent` with `output_key='serp_findings'`, wrapped in a
  > `SequentialAgent`. No tools yet — have it return a placeholder. Comment how `output_key` writes to
  > `session.state`."
- **Test:** run in the dev UI; open the **State tab** and confirm `serp_findings` appears.
- **Done when:** you can see the key land in state.

### M2 — The chain (state hand-off)
- **Goal:** baton passing between agents.
- **Paste:**
  > "Add `angle_finder` (`output_key='angle_brief'`) and `drafter` (`output_key='draft'`) after
  > `serp_analyst` in the `SequentialAgent`. Inject upstream keys into each instruction using `{key}`
  > substitution per section 11. Still no external tools."
- **Test:** run; in the State tab watch `serp_findings → angle_brief → draft` appear in order.
- **Done when:** all three keys populate in sequence.

### M3 — Wire the MCP servers
- **Goal:** real tools via MCP (banks the MCP concept).
- **Paste:**
  > "Connect the two MCP servers in section 9 using ADK's MCPToolset and `config/mcp_servers.yaml`.
  > Give `search` to `serp_analyst`; give `fetch` to `serp_analyst` too. Keep keys in `.env`. On
  > startup, log the discovered tool names to verify the handshake."
- **Test:** startup logs list a `search` and a `fetch` tool; `serp_analyst` now returns real source
  summaries with `common_claims`.
- **Done when:** eval case `serp_reads_top_pages_001` passes.

### M4 — Security: policy callback + output guard
- **Goal:** the differentiator.
- **Paste:**
  > "Implement `agents/callbacks/policy.py` as an after-tool callback on `fetch` per section 12:
  > structural allowlist check against `config/allowlist.yaml`, then a semantic Gemini ToU/PII check;
  > on fail, drop the content and append to `policy_notes`. Add `editor_guard`
  > (`output_key='final_article'`) that slop-cleans and strips PII. Comment the separation of
  > execution vs governance."
- **Test:** add a non-allowlisted domain and an email in a draft; confirm the source is skipped and
  the email stripped, both logged in `policy_notes`.
- **Done when:** eval cases `guard_strips_pii_001` and the ToU scenario pass.

### M5 — `trend_scout` + the first HITL gate
- **Goal:** make it proactive.
- **Paste:**
  > "Add `trend_scout` as the first agent: reads `topic_seeds`, uses the `search` MCP, writes
  > `topic_candidates`, and surfaces 2–3 angles for the human to choose; the chosen one becomes
  > `topic`. Handle the 'no fresh trend' fallback in section 11.2."
- **Test:** run; confirm 2–3 candidates appear and the chosen topic flows into `serp_analyst`.
- **Done when:** the candidate → selection → pipeline flow works.

### M6 — `voice_profile_builder` onboarding
- **Goal:** the voice magic.
- **Paste:**
  > "Implement `agents/onboarding/voice_profile_builder.py`: a run-once agent using a Gemini
  > multimodal model that accepts an audio file path + 3 text answers, extracts the `voice_profile`
  > schema (section 10), and persists it to `profile/voice_profile.json`. Then have `drafter` load and
  > use it. Discard raw audio after extraction. Handle the too-short-clip edge case."
- **Test:** run onboarding on a sample clip; confirm `voice_profile.json` is created and the next
  draft visibly matches the voice.
- **Done when:** drafts read in the user's voice and `voice_profile.json` is gitignored.

### M7 — Evaluate, (optionally) deploy, record
- **Goal:** ship + capture the video.
- **Eval (done):** ADK-native suite — `pytest` + `InMemoryRunner` (the Vertex-backed `agents-cli
  eval` can't introspect MCP toolsets). Run with `uv run pytest tests/`; all 6 cases green.
- **Deploy (optional):** `agents-cli deploy` to Agent Engine runs through Vertex/GCP — the same
  friction class as the eval. **Not required for judging.** Document a reproducible *local run* in
  `README.md` + note the deploy path (Dockerfile present). Do it only if time allows.
- **Record:** the demo (journey steps 2→5, with a security block + the Content Run Report on camera).
- **Done when:** eval suite green, README reproduces locally, demo recorded.

---

## 16. Deployment

```yaml
deploy:
  status: "NOT deployed — optional; deploy runs through Vertex/GCP (friction; not required for judging)"
  command: "agents-cli deploy"     # to Agent Engine, if pursued
  local_run: "agents-cli playground  (README documents env, install, and how to reproduce locally)"
  artifacts: "Dockerfile present; the system is architected to deploy, documented for reproducibility"
  note: "Live deployment is NOT required for judging. A documented local run satisfies the project link."
```

---

## 17. Testing strategy (summary)

- **Per-agent, visually:** the ADK dev UI **State tab** after every milestone — see which key each
  agent writes. This is your primary debugging and learning tool.
- **Automated:** the three EDD eval cases in `specs/evals/`, run via `agents-cli eval`.
- **Behavioural:** the BDD scenarios in `specs/scenarios.md`, including all edge cases.
- **Security:** deliberately feed a non-allowlisted domain and an email; confirm both are caught.

---

## 18. Roadmap (Phase 2 — for the writeup's "what's next")

- **Proprietary-evidence backing** — vector search over SME transcripts / first-party data so the
  angle is backed by evidence the competition can't access (the enterprise version of "non-commodity").
- **Brand-rules / compliance layer** — `brand_rules.yaml` (banned claims, required disclaimers,
  mandatory tone) enforced by `editor_guard` and surfaced in the run report — the governance feature
  enterprises actually buy.
- Internal/external link insertion with live 404 + scrape validation.
- Transcript ingestion for proprietary input.
- Real Google Trends API integration once general availability lands.
- Live conversational voice onboarding (frontend with mic + TTS).
- Multi-topic batch runs via `LoopAgent`.
- Delivery action via MCP (Google Doc / Drive / email-for-review) so the agent acts in a business system.
- Observability + an editorial dashboard.

---

## 19. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Setup/auth eats an evening (you're agent-reliant) | M0 is its own milestone; keep scope at the MVP; use the State tab to see failures |
| Accidental API key in code | `os.getenv()` everywhere; `.env.example` with names only; `.gitignore` from the start |
| Live scraping breaks / ToU issues | Two MCP servers only; allowlist + semantic policy check; failures degrade gracefully |
| Voice onboarding scope-creep | Upload-and-analyse (not live voice); Gemini ingests audio directly — no audio infra |
| Video underestimated | The user journey is the script; record right after M7 while it's fresh |
```
