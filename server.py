import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logging

from google.adk.agents.runner import InMemoryRunner
from google.genai import types
from agents.orchestrator import content_pipeline_agent

app = FastAPI(title="UniqVoice Content Pipeline")
logger = logging.getLogger(__name__)

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

class RunRequest(BaseModel):
    topic: str

@app.post("/api/run")
async def run_pipeline_no_hitl(req: RunRequest):
    runner = InMemoryRunner(agent=content_pipeline_agent)
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(req.topic)])
    
    logger.info(f"Starting no-HITL run for topic: {req.topic}")
    
    async for event in runner.run_async(new_message=initial_msg):
        # If trend_scout asks for input, automatically reply
        if event.tool_calls:
            for tc in event.tool_calls:
                if tc.function_call and tc.function_call.name == "request_input":
                    logger.info("Auto-replying to request_input with 'Option 1'")
                    auto_reply = types.Content(role="user", parts=[types.Part.from_text("I choose option 1.")])
                    async for _ in runner.run_async(new_message=auto_reply):
                        pass
                    break
                    
    state = runner.session.state
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
