# main.py
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional

from fastapi import FastAPI, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# -----------------------------------------------------------------------------
# App + CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="SignCall Backend (No-Call Mode)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# In-memory stores  (OK for demos; swap for a DB in production)
# -----------------------------------------------------------------------------
USERS: Dict[str, str] = {}  # email -> pw_hash
MESSAGES: Dict[str, List[dict]] = defaultdict(list)         # user_id -> [{content, emoji, language, timestamp}]
CUSTOM_GESTURES: Dict[str, List[dict]] = defaultdict(list)  # user_id -> [{name, seq_json}]
SOS_LOG: List[dict] = []                                    # recent SOS pings

SALT = "signcall_demo_salt_v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_pw(pw: str) -> str:
    return hashlib.sha256((SALT + pw).encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Auth (email == user_id for demo)
# -----------------------------------------------------------------------------
@app.post("/signup")
async def signup(email: str = Query(...), password: str = Query(...)):
    if not email or not password or len(password) < 6:
        return JSONResponse({"ok": False, "error": "Invalid email or password too short"}, status_code=400)
    if email in USERS:
        return JSONResponse({"ok": False, "error": "User already exists"}, status_code=409)
    USERS[email] = hash_pw(password)
    return {"ok": True, "user_id": email}


@app.post("/login")
async def login(email: str = Query(...), password: str = Query(...)):
    if email not in USERS:
        return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=401)
    if USERS[email] != hash_pw(password):
        return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=401)
    return {"ok": True, "user_id": email}


# -----------------------------------------------------------------------------
# Chat & history
# -----------------------------------------------------------------------------
@app.post("/message")
async def post_message(
    user_id: str = Query(...),
    content: str = Query(""),
    emoji: str = Query(""),
    language: str = Query("en"),
):
    MESSAGES[user_id].append(
        {
            "content": content,
            "emoji": emoji,
            "language": language,
            "timestamp": now_iso(),
        }
    )
    return {"ok": True}


@app.get("/history/{user_id}")
async def get_history(user_id: str):
    return JSONResponse(MESSAGES.get(user_id, []))


@app.delete("/history/{user_id}")
async def clear_history(user_id: str):
    MESSAGES[user_id].clear()
    return {"ok": True}


# -----------------------------------------------------------------------------
# Translation (stub) – replace with a real service if you want
# -----------------------------------------------------------------------------
@app.get("/translate")
async def translate(text: str = Query(""), lang: str = Query("en")):
    # Demo: echo the same text back (so the UI flow works).
    # Swap with a real translator (LibreTranslate/GCloud/Azure) later.
    return {"translated": text}


# -----------------------------------------------------------------------------
# Custom gesture endpoints
# -----------------------------------------------------------------------------
@app.get("/custom_gesture/samples")
async def list_gesture_samples(user_id: str = Query(...)):
    return JSONResponse(CUSTOM_GESTURES.get(user_id, []))


@app.post("/custom_gesture/save")
async def save_gesture_sample(
    user_id: str = Query(...),
    name: str = Query(...),
    sample_idx: int = Query(0),
    body: dict = Body(...),  # expects {"frames": [[63 floats per frame] * 36]}
):
    if not isinstance(body, dict) or "frames" not in body:
        return JSONResponse({"ok": False, "error": "Invalid body"}, status_code=400)
    CUSTOM_GESTURES[user_id].append({"name": name, "seq_json": body})
    return {"ok": True, "count": len(CUSTOM_GESTURES[user_id])}


# -----------------------------------------------------------------------------
# SOS (for Voice Assistant)
# -----------------------------------------------------------------------------
@app.post("/sos")
async def sos(
    user_id: str = Query(...),
    note: str = Query(""),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
):
    item = {
        "user_id": user_id,
        "note": note,
        "lat": lat,
        "lon": lon,
        "timestamp": now_iso(),
    }
    SOS_LOG.append(item)
    # In production: trigger SMS/Whatsapp/webhook here.
    return {"ok": True, "saved": item}


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True, "time": now_iso()}