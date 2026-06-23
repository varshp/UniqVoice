import asyncio
from google.adk.runners import InMemoryRunner
from agents.agent import app
from google.genai import types

async def main():
    runner = InMemoryRunner(app=app)
    session = await runner.session_service.create_session(app_name="agents", user_id="test_user")
    print(f"Session created with id {session.session_id} and state: {session.state}")
    
    # Try seeding state
    session.state["draft"] = "Seeded draft content"
    await runner.session_service.update_session(session)
    
    # Load back to check
    session = await runner.session_service.get_session(session.session_id)
    print(f"Session retrieved state: {session.state}")
    
    # Check run_async signature by passing a prompt and targeting an agent
    async for event in runner.run_async(session.session_id, input=types.Part.from_text("hello"), agent_name="editor_guard"):
        if hasattr(event, 'actions') and hasattr(event.actions, 'state_delta'):
            print(f"Event delta: {event.actions.state_delta}")
    
    print("Done")

if __name__ == "__main__":
    asyncio.run(main())
