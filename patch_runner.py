import re

with open("server.py", "r", encoding="utf-8") as f:
    code = f.read()

# Fix /api/scout
scout_orig = """    run_id = str(uuid.uuid4())
    runner = InMemoryRunner(agent=root_agent)
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(text=req.topic)])
    
    gen = runner.run_async(new_message=initial_msg)"""
scout_new = """    runner = InMemoryRunner(agent=root_agent)
    session = await runner.session_service.create_session(app_name="agents", user_id="test")
    run_id = session.id
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(text=req.topic)])
    
    gen = runner.run_async(user_id="test", session_id=session.id, new_message=initial_msg)"""
code = code.replace(scout_orig, scout_new)

# Fix /api/resume
resume_orig = """    async for _ in runner.run_async(new_message=auto_reply):
        pass
        
    state = runner.session.state"""
resume_new = """    async for _ in runner.run_async(user_id="test", session_id=req.run_id, new_message=auto_reply):
        pass
        
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=req.run_id)
    state = session.state"""
code = code.replace(resume_orig, resume_new)

# Fix /api/run
run_orig = """    runner = InMemoryRunner(agent=root_agent)
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(text=req.topic)])
    
    logger.info(f"Starting no-HITL run for topic: {req.topic}")
    
    async for event in runner.run_async(new_message=initial_msg):"""
run_new = """    runner = InMemoryRunner(agent=root_agent)
    session = await runner.session_service.create_session(app_name="agents", user_id="test")
    initial_msg = types.Content(role="user", parts=[types.Part.from_text(text=req.topic)])
    
    logger.info(f"Starting no-HITL run for topic: {req.topic}")
    
    async for event in runner.run_async(user_id="test", session_id=session.id, new_message=initial_msg):"""
code = code.replace(run_orig, run_new)

run_auto_orig = """                    async for _ in runner.run_async(new_message=auto_reply):
                        pass
                    break
                    
    state = runner.session.state"""
run_auto_new = """                    async for _ in runner.run_async(user_id="test", session_id=session.id, new_message=auto_reply):
                        pass
                    break
                    
    session = await runner.session_service.get_session(app_name="agents", user_id="test", session_id=session.id)
    state = session.state"""
code = code.replace(run_auto_orig, run_auto_new)

with open("server.py", "w", encoding="utf-8") as f:
    f.write(code)
