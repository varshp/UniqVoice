from dotenv import load_dotenv
load_dotenv()
import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging

from google.adk.runners import InMemoryRunner
from google.genai import types
from agents.orchestrator import root_agent

app = FastAPI(title="UniqVoice Content Pipeline")
logger = logging.getLogger(__name__)

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")


import uuid
from typing import Dict, Any

sessions: Dict[str, Any] = {}


from fastapi import UploadFile, File
import shutil
import os
import json
from agents.onboarding.voice_profile_builder import build_voice_profile

@app.post("/api/voice-upload")
async def voice_upload(audio: UploadFile = File(...)):
    temp_path = f"/tmp/{audio.filename}"
    with open(temp_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)
        
    success = build_voice_profile(temp_path, text_answers=[])
    
    if success:
        profile_path = os.path.join(os.path.dirname(__file__), "profile", "voice_profile.json")
        if os.path.exists(profile_path):
            with open(profile_path, "r") as f:
                return json.load(f)
                
    return {"error": "Failed to build voice profile"}

class ScoutRequest(BaseModel):
    topic: str

@app.post("/api/scout")
async def scout(req: ScoutRequest):
    runner = InMemoryRunner(agent=root_agent, app_name="agents")
    session = await runner.session_service.create_session(app_name="agents", user_id="test")
    run_id = session.id
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(text=req.topic)])
    
    gen = runner.run_async(user_id="test", session_id=session.id, new_message=initial_msg)
    
    candidates_text = ""
    async for event in gen:
        if getattr(event, "tool_calls", None):
            for tc in getattr(event, "tool_calls", []):
                if getattr(tc, "function_call", None) and getattr(tc.function_call, "name", None) in ["request_input", "adk_request_input"]:
                    args = getattr(tc.function_call, "args", {})
                    logger.info(f"ARGS IS: {args}, type: {type(args)}")
                    if args and "message" in args:
                        candidates_text = args["message"]
                    elif args and "prompt" in args:
                        candidates_text = args["prompt"]
                    else:
                        candidates_text = str(args)
                
    sessions[run_id] = (runner, gen)
    
    # Basic parsing of candidates_text into a list
    # We'll split by newlines and try to find numbered items or just return the raw text
    import re
    parsed_candidates = []
    for line in candidates_text.split("\n"):
        line = line.strip()
        if re.match(r"\d+\.", line) or line.startswith("-") or line.startswith("*"):
            parsed_candidates.append(line)
    
    if not parsed_candidates:
        parsed_candidates = [candidates_text] # fallback
    
    return {
        "run_id": run_id,
        "topic_candidates": parsed_candidates,
        "topic": req.topic
    }

class ResumeRequest(BaseModel):
    run_id: str
    chosen_index: int

@app.post("/api/resume")
async def resume(req: ResumeRequest):
    if req.run_id not in sessions:
        return {"error": "Session not found"}
        
    runner, gen = sessions.pop(req.run_id)
    choice_text = f"I choose option {req.chosen_index + 1}."
    
    logger.info(f"Resuming run {req.run_id} with choice {req.chosen_index + 1}")
    
    auto_reply = types.Content(role="user", parts=[types.Part.from_text(text=choice_text)])
    
    async for _ in runner.run_async(user_id="test", session_id=req.run_id, new_message=auto_reply):
        pass
        
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=req.run_id)
    state = session.state
    return {
        "final_article": state.get("final_article", ""),
        "run_report": state.get("run_report", ""),
        "policy_notes": state.get("policy_notes", ""),
        "voice_profile": state.get("voice_profile", {}),
        "angle_brief": state.get("angle_brief", {}),
        "serp_findings": state.get("serp_findings", {}),
        "topic": state.get("topic", req.topic),
    }

class RunRequest(BaseModel):
    topic: str

@app.post("/api/run")
async def run_pipeline_no_hitl(req: RunRequest):
    runner = InMemoryRunner(agent=root_agent, app_name="agents")
    session = await runner.session_service.create_session(app_name="agents", user_id="test")
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(text=req.topic)])
    
    logger.info(f"Starting no-HITL run for topic: {req.topic}")
    
    gen = runner.run_async(user_id="test", session_id=session.id, new_message=initial_msg)
    
    needs_input = False
    async for event in gen:
        if getattr(event, "tool_calls", None):
            for tc in getattr(event, "tool_calls", []):
                if getattr(tc, "function_call", None) and getattr(tc.function_call, "name", None) in ["request_input", "adk_request_input"]:
                    needs_input = True
                    
    if needs_input:
        logger.info("Auto-replying to request_input with 'Option 1'")
        auto_reply = types.Content(role="user", parts=[types.Part.from_text(text="I choose option 1.")])
        async for _ in runner.run_async(user_id="test", session_id=session.id, new_message=auto_reply):
            pass
                    
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    state = session.state
    return {
        "final_article": state.get("final_article", ""),
        "run_report": state.get("run_report", ""),
        "policy_notes": state.get("policy_notes", ""),
        "voice_profile": state.get("voice_profile", {}),
        "angle_brief": state.get("angle_brief", {}),
        "serp_findings": state.get("serp_findings", {}),
        "topic": state.get("topic", req.topic),
    }

@app.get("/")
async def tone_screen():
    return FileResponse(os.path.join("web", "index.html"))

@app.get("/tone-captured")
async def tone_captured_screen():
    return FileResponse(os.path.join("web", "tone_captured.html"))

@app.get("/angle")
async def angle_screen():
    return FileResponse(os.path.join("web", "angle.html"))

@app.get("/create")
async def create_screen():
    return FileResponse(os.path.join("web", "create.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
