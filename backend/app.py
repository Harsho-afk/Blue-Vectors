from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from collector import collect_async

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/collect/{platform}/{username}")
async def collect(platform: str, username: str, limit: int = 50):
    try:
        profile = await collect_async(platform, username, limit=limit)
        return profile.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
