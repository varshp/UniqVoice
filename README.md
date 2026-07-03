# UniqVoice

**A voice-aware content engine that finds the angle nobody else is taking, writes it in your own voice, and proves what the run cost.**

Built on Google's Agent Development Kit (ADK) as a sequential multi-agent pipeline.
Capstone · *Agents for Business* track · 5-Day AI Agents Intensive (Vibe Coding) with Google.

---

## The problem

AI made content infinite — and identical. Everyone prompts the same models, so everyone
publishes the same take in the same flat voice. In a world where AI answer engines summarize
the web, *sounding like everyone else doesn't just make you boring — it makes you invisible.*

For a business, that's a real cost. Content is a budget line measured in agency retainers and
team hours; undifferentiated content doesn't rank, doesn't get cited, and doesn't convert; and
off-brand or non-compliant content is a liability. The two hardest parts of the job are exactly
the parts generic AI tools skip:

1. **Finding an angle nobody else has taken** — most tools rewrite the consensus, adding to the slop.
2. **Keeping it authentically in *your* voice** — most tools give you the average take in a generic voice.

UniqVoice is built to do both, with a human in control of the decisions that matter and an
auditable record of what every run cost and where its facts came from.

## Why agents (not one prompt)

This is genuinely multi-step work, and each step needs a different skill and a different tool:
scout a topic, research what already ranks, reason about the gap, write in a learned voice,
enforce governance, and report the run. A single prompt would have to do all of it at once —
which is exactly where quality collapses. UniqVoice splits the job into **specialised agents that
pass a shared state "baton" down a chain**, so each step stays sharp, debuggable, and individually
testable (ADK's "reduction of search space" — fewer tools per agent, fewer wrong moves).

---

## How it works

### Onboarding (runs once) — learn the voice
You record a ~1-minute clip in your normal speaking voice. `voice_profile_builder` feeds the
**raw audio directly** to a multimodal Gemini model (no transcription step — a transcript would
throw away rhythm, emphasis, and cadence, which are exactly what define a voice) and extracts a
persistent `voice_profile`: tone, sentence rhythm, rhetorical moves, and an explicit *avoid-list*.
The profile is saved once and applied to every future run.

### Pipeline (per article) — a `SequentialAgent` of six sub-agents
`trend_scout → serp_analyst → angle_finder → drafter → editor_guard → report_builder`

| Agent | Does | Writes to state |
|---|---|---|
| `trend_scout` | Proposes 2–3 candidate angles on your subject (search via MCP). **You pick one.** | `topic_candidates`, `topic` |
| `serp_analyst` | Reads the top-ranking pages, extracts the consensus "commodity" take (search + fetch via MCP). | `serp_findings` (sources + `common_claims`) |
| `angle_finder` | Finds the gap — an angle that reframes or contradicts the consensus. | `angle_brief` (`angle`, `why_new`, outline) |
| `drafter` | Writes the article to the brief **in your voice** (uses `voice_profile`). | `draft` |
| `editor_guard` | Slop-cleans and strips PII; logs every action. | `final_article`, `policy_notes` |
| `report_builder` | Assembles the Content Run Report (reads state only). | `run_report` |

Each agent reads only the keys it needs and writes exactly one via `output_key`. Two
**human-in-the-loop gates** keep the user in control: *pick the angle*, and *approve the final
article before any publish*.

#### State flow (the baton)

The agents pass work through shared `session.state`. The full read/write picture:

| Agent | Reads | Writes |
|---|---|---|
| `trend_scout` | `explicit_topic_request`, `topic_seeds` | `topic_candidates`, `topic` |
| `serp_analyst` | `topic` | `serp_findings` (sources + `common_claims`) |
| `angle_finder` | `serp_findings`, `explicit_topic_request` | `angle_brief` (`angle`, `why_new`, outline) |
| `drafter` | `angle_brief`, `voice_profile`, `tone_notes`, `explicit_topic_request` — **not `serp_findings`** | `draft` |
| `editor_guard` | `draft` | `final_article`, `policy_notes` |
| `report_builder` | (all, read-only) | `run_report` |

**A deliberate design choice — the drafter is isolated from the source text.** It reads the
*differentiated brief* and your *voice profile*, but **never** the raw `serp_findings`. This physical
separation stops the drafter from absorbing the generic style of the top-ranking articles or echoing
the commodity consensus — it's forced to write from your voice and the unique angle alone.

The trade-off (named honestly): because the drafter doesn't see the source text, the draft's specific
facts aren't directly grounded in the fetched sources. That's why UniqVoice surfaces its sources
transparently in the run report and gates every article behind human approval — the human is where
factual accuracy is checked. The natural next step (see roadmap) is passing *source-attributed facts*
into the brief, which would add grounding without sacrificing the drafter's style-independence.

### Architecture diagram
See [`UniqVoice_Architecture.png`](UniqVoice_Architecture.png) for the full diagram
(onboarding flow, the six-agent pipeline, MCP tools, the policy guard, and the two HITL gates).

---

## Course concepts demonstrated

The capstone requires **at least three**. UniqVoice demonstrates four solidly, plus extras:

| Concept | Where it lives |
|---|---|
| **Multi-agent system (ADK)** | `SequentialAgent` orchestrator + 6 pipeline sub-agents + 1 onboarding agent |
| **MCP servers** | Tavily `search` + `mcp-server-fetch`, wired as agent tools via `MCPToolset` |
| **Security features** | semantic ToU/PII guard + hard fetch cap + output PII strip + 2 HITL gates |
| **Agent skills / Agents CLI + eval** | `agents-cli` setup & playground; an ADK-native eval suite (`pytest` + `InMemoryRunner`) |
| *Antigravity* | the project was built in Antigravity |
| *Multimodal voice onboarding* | `voice_profile_builder` learns voice from raw audio |
| *Business ROI artifact* | the Content Run Report's cost/time panel |

---

## The Content Run Report — accountability, on every run

Every run ends with a one-page report (`outputs/run_report_<timestamp>.md`) that turns "AI that
writes" into "an accountable, governed, costed content run":

1. **The take** — the chosen angle and *why it's non-commodity* (not the consensus).
2. **Sources & governance** — the sources used, plus the full `policy_notes` trail: what was
   fetched, what was blocked (ToU/PII), and whether the fetch cap was hit.
3. **Voice match** — confirmation the draft was written against the loaded voice profile.
4. **ROI panel** — estimated model cost and wall-clock time for the run vs a configurable human
   baseline (e.g. `~$0.10 / under 2 minutes` vs `~$300 / 1 day` for an agency draft). Costs are computed
   from real token usage where available and clearly labelled as estimates otherwise.

---

## Security & governance

The policy layer **evolved during the build**, and the final design is general-purpose:

- **Started** as a strict domain *allowlist gate* — but that starved non-marketing topics (a
  finance query returned finance sources not on a marketing allowlist, blocking everything and
  causing a retry loop).
- **Redesigned** into a **semantic-first guard**: domains are allowed by default except a small
  `blocklist.yaml`; a semantic Gemini check on every fetched page enforces **terms-of-use and PII**;
  a **hard fetch cap is enforced in code** (not just in a prompt) so the pipeline can never loop;
  and `editor_guard` does a final PII strip on the article. The original allowlist is retained only to flag unfamiliar domains in the audit trail, not to block them.
- Every decision is written to `policy_notes`, which doubles as a human-readable **audit trail**.

🚨 **No API keys or secrets are committed.** All credentials are read via `os.getenv()`;
`.env.example` lists key *names* only; `.env`, `profile/`, and audio files are gitignored.

---

## Tech stack

- **Google ADK** — `SequentialAgent`, `LlmAgent`, callbacks, `InMemoryRunner`
- **agents-cli** — project setup, local playground
- **MCP** — `tavily-mcp` (search) + `mcp-server-fetch` (fetch) via `MCPToolset`
- **Gemini** — 2.5-flash for high-throughput steps, 2.5-pro for reasoning gates, and 3.5-flash for multimodal onboarding
- **Antigravity** — the build environment
- **pytest** — the ADK-native evaluation suite

### Model assignments

| Agent | Model |
| --- | --- |
| `voice_profile_builder` | `gemini-3.5-flash` (multimodal audio) |
| `trend_scout` | `gemini-2.5-flash` |
| `serp_analyst` | `gemini-2.5-flash` |
| `angle_finder` | `gemini-2.5-pro` |
| `drafter` | `gemini-2.5-flash` |
| `editor_guard` | `gemini-2.5-pro` |
| `report_builder` | none (pure-Python `BaseAgent`) |
| policy semantic check | `gemini-2.5-flash` |

> **Routing by capability.** Fast, cheap `gemini-2.5-flash` handles the high-throughput steps: `trend_scout`, `serp_analyst`, `drafter`, and the policy content scan. `gemini-2.5-pro` is reserved for the two reasoning-heavy gates: `angle_finder`, which deduces the contrarian gap, and `editor_guard`, which handles stricter governance. Multimodal onboarding uses `gemini-3.5-flash`. All models are env-configurable, so they can be swapped without touching agent code.

---

## Setup & running locally

> Live deployment is **not required for judging**; this project runs locally via the steps below.
> It is architected to deploy to Agent Engine via `agents-cli deploy` (a `Dockerfile` is included).

### Prerequisites
- Python ≥ 3.11
- [`uv`](https://github.com/astral-sh/uv) (or `pip`)
- `npx` (for the Tavily MCP server) and `uvx` (for the fetch MCP server)
- A **Gemini API key** (Google AI Studio) and a free **Tavily API key**

### 1. Install
```bash
git clone https://github.com/varshp/UniqVoice.git
cd UniqVoice
uv sync            # or: pip install -r requirements.txt
```

### 2. Configure secrets
Copy the example file and fill in your keys (names only shown here — never commit real values):
```bash
cp .env.example .env
```
```
# .env
GOOGLE_API_KEY=your-gemini-key
GEMINI_API_KEY=your-gemini-key   # same value; both are read
TAVILY_API_KEY=your-tavily-key
```

### 3. Onboard your voice (once)
Record a ~1-minute clip (talk naturally about what you write) and run:
```bash
uv run python scripts/run_onboarding.py myvoice.m4a
```
This creates `profile/voice_profile.json` (gitignored).

### 4. Run the pipeline
```bash
agents-cli playground
# open http://127.0.0.1:8080/dev-ui/?app=agents
```
Type a topic, pick an angle at the gate, and watch the pipeline produce a final article plus a
run report in `outputs/`.

> **Note:** `.env` is read at server launch — restart the playground after editing it.

---

## Evaluation

UniqVoice ships with an **ADK-native eval suite** (`pytest` + ADK `InMemoryRunner`, which runs the
real agent including its MCP tools). Run it with:

```bash
uv run pytest tests/
```

The full suite passes — 10 tests, including the six core eval cases below and the integration tests. The suite mixes **deterministic assertions** (for structured logic) with
**LLM-as-a-judge** checks (for subjective generative output that a keyword or regex test couldn't
fairly evaluate), and includes two **regression tests** for bugs found and fixed during the build:

1. **`serp_reads_top_pages`** — parses the `serp_analyst` output and asserts it extracted ≥2 real sources and synthesised a non-empty `common_claims` array (the commodity consensus to differentiate against). *Deterministic.*
2. **`angle_is_non_commodity`** — passes the generated `angle_brief` to an independent Gemini judge instance that returns PASS/FAIL on whether the angle meaningfully reframes or contradicts the consensus (rather than restating it), whether `why_new` explains the differentiation, and whether the outline has ≥4 beats. *LLM-as-a-judge.*
3. **`voice_applied`** — injects a stylised voice profile (e.g. narrative open, revelation-style close) and uses a Gemini judge to verify the final draft actually executes those rhetorical moves — the kind of subjective check a keyword test can't do reliably. *LLM-as-a-judge.*
4. **`guard_strips_pii`** — injects raw emails/phone numbers into a draft and asserts `editor_guard` removes them *and* logs the action to the `policy_notes` audit trail. *Deterministic.*
5. **`security_blocks_no_loop`** *(regression)* — built after a live bug: proves that against a run of blocked pages, the code-enforced fetch cap fires and the pipeline completes instead of looping. *Deterministic.*
6. **`subject_anchored`** *(regression)* — ensures an explicit subject (e.g. "SpaceX") survives the human-in-the-loop transition and anchors the whole downstream pipeline through to a completed run report. *Deterministic.*

Using an LLM judge to grade subjective outputs (voice adoption, contrarian angle) instead of brittle
keyword checks is a deliberate choice for testing generative systems, where the "correct" answer
isn't a fixed string.

> The suite was originally authored for `agents-cli eval`, but the Vertex-backed eval SDK can't
> introspect ADK `MCPToolset` objects, so it was moved to an ADK-native `InMemoryRunner` harness —
> a real tooling-fit decision.

---

## Repository structure

```
uniqvoice/
├── agents/
│   ├── orchestrator.py            # SequentialAgent + before_agent_callback (loads voice profile)
│   ├── sub_agents/                # trend_scout, serp_analyst, angle_finder, drafter, editor_guard, report_builder
│   ├── onboarding/                # voice_profile_builder (multimodal audio → voice_profile)
│   └── callbacks/                 # policy.py — the semantic security guard
├── config/                        # allowlist.yaml, blocklist.yaml, cost.yaml, mcp_servers.yaml
├── profile/                       # voice_profile.json (gitignored)
├── outputs/                       # generated run reports
├── scripts/run_onboarding.py      # one-time voice onboarding CLI
├── specs/SPEC.md                  # the build spec (source of truth)
├── tests/                         # ADK-native eval suite
├── content_engine_architecture.html
├── .env.example                   # key names only
├── Dockerfile
└── requirements.txt
```

---

## Design decisions & build journey

A few key decisions:

- **Semantic-first security, not an allowlist gate** — a fixed allowlist starved general topics; a
  content-aware ToU/PII guard + a code-enforced fetch cap is general-purpose *and* still blocks.
- **Subject vs angle are separate** — a subtle bug let a chosen angle drop the subject ("SpaceX")
  and send the whole pipeline generic. Fixed by persisting the subject (`explicit_topic_request`)
  through the pipeline; a regression test now locks it in.
- **Voice from audio, not a transcript** — a transcript discards the very signal that defines voice.
- **Explicit topic always beats the profile's topic seeds** — a persistent profile must never
  override what the user actually typed.
- **Honest cost reporting** — real token usage where available; estimates clearly labelled; a
  defensible human baseline. Understatement is credibility.

---

## Roadmap (what's next)

- **Proprietary-evidence backing** — vector search over first-party data / SME transcripts so the
  angle is backed by evidence competitors can't access.
- **Brand-rules / compliance layer** — `brand_rules.yaml` (banned claims, required disclaimers)
  enforced by `editor_guard` and surfaced in the run report.
- **Delivery action via MCP** — push the approved article + report to a Google Doc / Drive / email.
- **Live conversational onboarding**, multi-topic batch runs (`LoopAgent`), and an editorial dashboard.

---

*Built solo, directing AI coding assistants, during the 5-Day AI Agents Intensive.*
