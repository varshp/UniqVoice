from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="UniqVoice Content Pipeline")

# Mount static files if needed (e.g. for CSS, JS, images)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

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
