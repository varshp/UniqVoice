from dotenv import load_dotenv
load_dotenv()
import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging
import json

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
        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for part in event.content.parts:
                tc = getattr(part, "function_call", None)
                if tc and getattr(tc, "name", None) in ["request_input", "adk_request_input"]:
                    args = getattr(tc, "args", {})
                    logger.info(f"ARGS IS: {args}, type: {type(args)}")
                    if args and "message" in args:
                        candidates_text = args["message"]
                    elif args and "prompt" in args:
                        candidates_text = args["prompt"]
                    else:
                        candidates_text = str(args)
                
    sessions[run_id] = (runner, gen)
    
    # Try parsing candidates_text as JSON
    parsed_candidates = []
    try:
        import re
        # Clean potential markdown fences from the LLM output
        clean_text = re.sub(r'```json\s*', '', candidates_text)
        clean_text = re.sub(r'```\s*', '', clean_text)
        
        import json
        data = json.loads(clean_text)
        if isinstance(data, list):
            parsed_candidates = data
        elif isinstance(data, dict) and "topic_candidates" in data:
            parsed_candidates = data["topic_candidates"]
        else:
            raise ValueError("Parsed JSON is not a list")
    except Exception as e:
        logger.error(f"Failed to parse request_input message as JSON: {e}. Raw text: {candidates_text}")
        # Fallback to basic string parsing if JSON fails
        import re
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
    
    async def event_generator():
        try:
            async for event in runner.run_async(user_id="test", session_id=req.run_id, new_message=auto_reply):
                if getattr(event, "content", None) and getattr(event.content, "parts", None):
                    for part in event.content.parts:
                        fc = getattr(part, "function_call", None)
                        if fc:
                            yield json.dumps({
                                "type": "tool_call",
                                "tool": fc.name,
                                "args": dict(fc.args) if hasattr(fc, "args") else {}
                            }) + "\n"
                        elif getattr(part, "text", None):
                            yield json.dumps({
                                "type": "text",
                                "text": part.text
                            }) + "\n"
        except Exception as e:
            logger.error(f"Error during run_async: {e}")
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
            
        session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=req.run_id)
        state = session.state
        final_data = {
            "type": "complete",
            "final_article": state.get("final_article", ""),
            "run_report": state.get("run_report", ""),
            "policy_notes": state.get("policy_notes", ""),
            "voice_profile": state.get("voice_profile", {}),
            "angle_brief": state.get("angle_brief", {}),
            "serp_findings": state.get("serp_findings", {}),
            "topic": state.get("topic", ""),
        }
        yield json.dumps(final_data) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

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
        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for part in event.content.parts:
                tc = getattr(part, "function_call", None)
                if tc and getattr(tc, "name", None) in ["request_input", "adk_request_input"]:
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

@app.get("/voice-loading")
async def voice_loading_screen():
    return FileResponse(os.path.join("web", "voice_loading.html"))

@app.get("/process-alignment")
async def process_alignment_screen():
    return FileResponse(os.path.join("web", "process_alignment.html"))

@app.get("/angle")
async def angle_screen():
    return FileResponse(os.path.join("web", "angle.html"))

@app.get("/create")
async def create_screen():
    return FileResponse(os.path.join("web", "create.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
