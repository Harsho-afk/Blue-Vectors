from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from collector import collect_async
from routes_auth import router as auth_router
from routes_cases import router as cases_router
from auth import get_current_user

app = FastAPI(title="ARIA API")

# ── CORS ──────────────────────────────────────────────────────────────────────
# IMPORTANT: allow_credentials=True requires an explicit origin list — NOT "*".
# Using "*" with credentials silently breaks cookie auth.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:80",
        "http://localhost:5173",
    ],
    allow_credentials=True,                    # Required for HttpOnly cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(cases_router)

# ── Existing routes ───────────────────────────────────────────────────────────
@app.get("/collect/{platform}/{username}")
async def collect(platform: str, username: str, limit: int = 50,
                  current_user: dict = Depends(get_current_user)):
    """Collect public profile data. Requires authentication."""
    try:
        profile = await collect_async(platform, username, limit=limit)
        return profile.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
