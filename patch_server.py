import re

with open("server.py", "r") as f:
    code = f.read()

new_code = """
import uuid
from typing import Dict, Any

sessions: Dict[str, Any] = {}

class ScoutRequest(BaseModel):
    topic: str

@app.post("/api/scout")
async def scout(req: ScoutRequest):
    run_id = str(uuid.uuid4())
    runner = InMemoryRunner(agent=content_pipeline_agent)
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(req.topic)])
    
    gen = runner.run_async(new_message=initial_msg)
    
    candidates_text = ""
    async for event in gen:
        if event.tool_calls:
            for tc in event.tool_calls:
                if tc.function_call and tc.function_call.name == "request_input":
                    # extract the prompt/message from the tool call
                    args = tc.function_call.args
                    if args and "message" in args:
                        candidates_text = args["message"]
                    elif args and "prompt" in args:
                        candidates_text = args["prompt"]
                    else:
                        candidates_text = str(args)
                    break
            if candidates_text:
                break
                
    sessions[run_id] = (runner, gen)
    
    # Basic parsing of candidates_text into a list
    # We'll split by newlines and try to find numbered items or just return the raw text
    import re
    parsed_candidates = []
    for line in candidates_text.split("\\n"):
        line = line.strip()
        if re.match(r"\\d+\\.", line) or line.startswith("-") or line.startswith("*"):
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
    
    auto_reply = types.Content(role="user", parts=[types.Part.from_text(choice_text)])
    
    async for _ in runner.run_async(new_message=auto_reply):
        pass
        
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
"""

if "class ScoutRequest" not in code:
    code = code.replace("class RunRequest(BaseModel):", new_code + "\nclass RunRequest(BaseModel):")

with open("server.py", "w") as f:
    f.write(code)
