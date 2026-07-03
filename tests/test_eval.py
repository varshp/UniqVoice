import os
import json
import pytest
import asyncio
from google.adk.runners import InMemoryRunner
from agents.agent import app
from agents.sub_agents.editor_guard import editor_guard_agent
from agents.sub_agents.angle_finder import angle_finder_agent
from agents.sub_agents.drafter import drafter_agent
from google.genai import types, Client

@pytest.fixture
def runner():
    return InMemoryRunner(app=app)

@pytest.mark.asyncio
async def test_serp_reads_top_pages_001(runner):
    """serp_analyst must aggregate >=2 sources and extract a commodity consensus."""
    session = await runner.session_service.create_session(app_name="agents", user_id="test")
    
    # Run the pipeline E2E
    # Turn 0: User gives topic. The pipeline hits request_input in trend_scout.
    events = []
    async for event in runner.run_async(user_id="test", session_id=session.id, new_message=types.Content(parts=[types.Part.from_text(text="why AI marketing pilots stall")])):
        events.append(event)
    
    # Turn 1: User selects candidate 1
    async for event in runner.run_async(user_id="test", session_id=session.id, new_message=types.Content(parts=[types.Part.from_text(text="1")])):
        events.append(event)
        
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    
    # Assert
    serp_findings = session.state.get("serp_findings")
    assert serp_findings, "serp_findings is empty"
    
    raw = serp_findings.strip()
    if raw.startswith("```json"):
        raw = raw[7:-3]
    elif raw.startswith("```"):
        raw = raw[3:-3]
        
    parsed = json.loads(raw.strip())
    assert len(parsed.get("sources", [])) >= 2, f"Expected >= 2 sources, got {len(parsed.get('sources', []))}"
    assert parsed.get("common_claims"), "common_claims is empty"


@pytest.mark.asyncio
async def test_guard_strips_pii_001(runner):
    """editor_guard must remove PII (email + phone) and log it to policy_notes."""
    runner_guard = InMemoryRunner(agent=editor_guard_agent, app_name="agents")
    session = await runner_guard.session_service.create_session(
        app_name="agents", user_id="test",
        state={
            "explicit_topic_request": "",
            "draft": "This is a great article. For questions, reach me at jane@acme.com or call 555-1234."
        }
    )
    
    # Run editor_guard directly
    async for event in runner_guard.run_async(user_id="test", session_id=session.id):
        pass
        
    session = await runner_guard.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    
    final_article = session.state.get("final_article", "")
    policy_notes = session.state.get("policy_notes", "")
    
    assert "jane@acme.com" not in final_article, "Email was not stripped from final_article"
    assert "555-1234" not in final_article, "Phone number was not stripped from final_article"
    assert "pii" in policy_notes.lower() or "stripped" in policy_notes.lower() or "removed" in policy_notes.lower(), "Policy notes didn't mention PII removal"


@pytest.mark.asyncio
async def test_angle_is_non_commodity_001(runner):
    """angle_finder must propose an angle that contradicts or meaningfully extends the common_claims."""
    runner_angle = InMemoryRunner(agent=angle_finder_agent, app_name="agents")
    session = await runner_angle.session_service.create_session(
        app_name="agents", user_id="test",
        state={
            "explicit_topic_request": "",
            "topic": "why AI marketing pilots stall",
            "topic_seeds": ["AI marketing ROI", "content quality vs quantity"],
            "serp_findings": json.dumps({
                "sources": [
                  { "url": "https://example.com/post1", "summary": "Use AI to write more posts faster." },
                  { "url": "https://example.com/post2", "summary": "AI tools help marketers scale content production." }
                ],
                "common_claims": [
                  "Use AI to write more posts faster",
                  "AI tools help scale content production"
                ]
            })
        }
    )
    
    async for event in runner_angle.run_async(user_id="test", session_id=session.id):
        pass
        
    session = await runner_angle.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    angle_brief_raw = session.state.get("angle_brief")
    assert angle_brief_raw is not None, "angle_brief not in state"
    
    # LLM-as-judge
    client = Client()
    prompt = f"""
    You are an expert judge reviewing an 'angle_brief'.
    The goal is to propose an angle that contradicts or meaningfully extends the common_claims.
    
    Angle Brief JSON:
    {angle_brief_raw}
    
    Does the 'angle' meaningfully differ from the common_claims (reframes, not restates)?
    Does 'why_new' explain this differentiation?
    Does the outline have at least 4 beats?
    
    Respond with exactly PASS or FAIL.
    """
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    assert "PASS" in resp.text, f"LLM judge failed angle_brief. Output: {resp.text}"


@pytest.mark.asyncio
async def test_subject_anchored_001(runner):
    """An explicit subject must survive candidate selection and the whole pipeline."""
    session = await runner.session_service.create_session(app_name="agents", user_id="test")
    session.state["explicit_topic_request"] = "is it a mistake to invest in SpaceX post-IPO"
    
    # E2E pipeline
    async for event in runner.run_async(user_id="test", session_id=session.id, new_message=types.Content(parts=[types.Part.from_text(text="is it a mistake to invest in SpaceX post-IPO")])):
        pass
        
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    async for event in runner.run_async(user_id="test", session_id=session.id, new_message=types.Content(parts=[types.Part.from_text(text="1")])):
        pass
        
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    candidates = session.state.get("topic_candidates", [])
    topic_candidates = " ".join([f"{c.get('title', '')} {c.get('description', '')}" for c in candidates])
    assert "SpaceX" in topic_candidates, f"SpaceX not in topic_candidates: {topic_candidates}"
    final_article = session.state.get("final_article", "")
    assert "SpaceX" in final_article, "SpaceX dropped from final_article"
    assert any(word in final_article for word in ["Starship", "Starlink", "Elon", "rocket", "post-IPO"]), "Final article lacks specific context"
    
    # Verify M7 run_report
    print(f"\n\nSTATE KEYS: {session.state.keys()}\n\n")
    run_report = session.state.get("run_report", "")
    assert run_report, "run_report not produced"
    assert "## 1. The Take" in run_report, "Missing Take section"
    assert "Unknown" not in run_report.split("## 2. Sources")[0], "Angle/Why New parsed as Unknown"
    assert "## 2. Sources & Governance" in run_report, "Missing Sources section"
    assert "## 3. Voice Match" in run_report, "Missing Voice Match section"
    assert "## 4. Final Article snippet" in run_report, "Missing Snippet section"
    assert "**ROI Panel**" in run_report, "Missing ROI Panel"
    # Basic sanity checks on the ROI headline
    assert "vs ~$" in run_report, "Missing cost comparison string"


@pytest.mark.asyncio
async def test_security_blocks_no_loop_001(runner):
    """The guard logs blocked sources and the fetch cap prevents loops."""
    session = await runner.session_service.create_session(app_name="agents", user_id="test")
    session.state["explicit_topic_request"] = "is it a mistake to invest in SpaceX post-IPO"
    
    async for event in runner.run_async(user_id="test", session_id=session.id, new_message=types.Content(parts=[types.Part.from_text(text="is it a mistake to invest in SpaceX post-IPO")])):
        pass
        
    async for event in runner.run_async(user_id="test", session_id=session.id, new_message=types.Content(parts=[types.Part.from_text(text="1")])):
        pass
        
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    fetch_count = session.state.get("fetch_attempt_count", 0)
    assert fetch_count <= 5, f"Fetch loop detected! Count: {fetch_count}"
    assert session.state.get("final_article"), "Final article was not produced"


@pytest.mark.asyncio
async def test_voice_applied_001(runner):
    """With a profile loaded, the draft reflects the captured voice."""
    runner_draft = InMemoryRunner(agent=drafter_agent, app_name="agents")
    session = await runner_draft.session_service.create_session(
        app_name="agents", user_id="test",
        state={
            "explicit_topic_request": "why AI marketing pilots stall",
            "topic": "why AI marketing pilots stall",
            "tone_notes": "",
            "angle_brief": json.dumps({
                "angle": "AI Pilots fail because of lack of strategy", 
                "why_new": "Contradicts the notion that technology is the barrier", 
                "outline": ["Introduction", "The Technology Fallacy", "Strategy First"], 
                "must_include": ["Concrete example of a failed pilot"]
            }),
            "voice_profile": {
                "tone": "direct, contrarian", 
                "sentence_rhythm": "short punchy openers", 
                "vocabulary": ["orchestrate", "leverage"], 
                "rhetorical_moves": ["ends on a revelation-style close", "opens with a narrative/scene rather than a generic thesis"], 
                "avoid": ["that's the plan"]
            }
        }
    )
    
    async for event in runner_draft.run_async(user_id="test", session_id=session.id):
        pass
        
    session = await runner_draft.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    draft = session.state.get("draft", "")
    assert "that's the plan" not in draft.lower(), "Avoid-list phrase found in draft"
    
    client = Client()
    prompt = f"""
    You are an expert judge reviewing an article draft.
    
    Draft:
    {draft}
    
    Did the article successfully adopt these voice profile rules:
    1. Ends on a revelation-style close.
    2. Opens with a narrative/scene rather than a generic thesis.
    
    Respond with exactly PASS or FAIL.
    """
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    assert "PASS" in resp.text, f"LLM judge failed voice check. Output: {resp.text}"

from agents.callbacks.policy import fetch_before_policy_callback
from google.adk.tools import BaseTool, ToolContext

@pytest.mark.asyncio
async def test_policy_allowlist_soft_gate():
    """A domain not in blocklist (and not in allowlist) should NOT be blocked before fetch."""
    class DummyTool:
        name = "fetch"
    tool = DummyTool()
    args = {"url": "https://random-unknown-domain.com/article"}
    
    class DummySession:
        id = "test-session"
        
    class DummyContext:
        session = DummySession()
        state = {"fetch_attempt_count": 0}
        
    tool_context = DummyContext()
    
    result = await fetch_before_policy_callback(tool, args, tool_context)
    
    # Must return None to allow the tool to proceed
    assert result is None
    assert tool_context.state["fetch_attempt_count"] == 1
    assert "not on allowlist" in tool_context.state.get("policy_notes", "")


@pytest.mark.asyncio
async def test_policy_blocklist_hard_gate():
    """A domain on the blocklist MUST be blocked before fetch."""
    class DummyTool:
        name = "fetch"
    tool = DummyTool()
    args = {"url": "https://example-content-farm.com/spam"}
    
    class DummySession:
        id = "test-session"
        
    class DummyContext:
        session = DummySession()
        state = {"fetch_attempt_count": 0}
        
    tool_context = DummyContext()
    
    result = await fetch_before_policy_callback(tool, args, tool_context)
    
    # Must return a dict blocking the fetch
    assert result is not None
    assert "content" in result
    assert "blocked by structural policy (domain on blocklist)" in result["content"][0]["text"]
