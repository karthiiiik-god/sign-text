# main.py
import hashlib
import hmac
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import json
import os

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
# Persistent stores
# -----------------------------------------------------------------------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

SALT = "signcall_demo_salt_v1"

def load_json(filename: str, default=None):
    """Load JSON, return default if missing or invalid."""
    if default is None:
        default = {}
    path = f"{DATA_DIR}/{filename}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(filename: str, data):
    """Save dict/list to JSON with indent"""
    path = f"{DATA_DIR}/{filename}"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def hash_pw(pw: str) -> str:
    return hashlib.sha256((SALT + pw).encode("utf-8")).hexdigest()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

def normalize_email(email: str) -> str:
    return (email or "").strip().lower()

def require_credentials(creds: Credentials, *, check_password_length: bool) -> tuple[str, str]:
    email = normalize_email(creds.email)
    password = creds.password
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if check_password_length and len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if not password.strip():
        raise HTTPException(status_code=400, detail="Enter a password.")
    return email, password

# Load persistent data on startup
USERS: Dict[str, str] = load_json("users.json")
MESSAGES = defaultdict(list)
for k, v in load_json("messages.json").items():
    MESSAGES[k] = v
CUSTOM_GESTURES = defaultdict(list)
for k, v in load_json("gestures.json").items():
    CUSTOM_GESTURES[k] = v
SOS_LOG: List[dict] = load_json("sos.json", [])
if not isinstance(SOS_LOG, list):
    SOS_LOG = []

# Built-in signs used by the dictionary and the live detector.
SIGNS: List[dict] = [
    {
        "name": "Hello",
        "emoji": "✌",
        "description": "Index and middle fingers extended in a V, other fingers folded.",
        "keywords": ["hello", "hi", "greet"],
        "media": "",
    },
    {
        "name": "Yes",
        "emoji": "👍",
        "description": "Thumb extended upward, other fingers folded.",
        "keywords": ["yes", "ok", "agree"],
        "media": "",
    },
    {
        "name": "No",
        "emoji": "👎",
        "description": "Thumb pointing down, other fingers folded.",
        "keywords": ["no", "disagree"],
        "media": "",
    },
]

# -----------------------------------------------------------------------------
# Auth (email == user_id)
# -----------------------------------------------------------------------------
@app.post("/signup")
async def signup(creds: Credentials):
    email, password = require_credentials(creds, check_password_length=True)
    if email in USERS:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    USERS[email] = hash_pw(password)
    save_json("users.json", USERS)
    return {"ok": True, "user_id": email}

@app.post("/login")
async def login(creds: Credentials):
    email, _password = require_credentials(creds, check_password_length=False)
    stored = USERS.get(email)
    digest = hash_pw(creds.password)
    if not isinstance(stored, str) or len(stored) != len(digest) or not hmac.compare_digest(stored, digest):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return {"ok": True, "user_id": email}

@app.get("/signs")
async def list_signs(q: str = Query("")):
    query = q.strip().lower()
    if not query:
        return SIGNS
    matches = []
    for sign in SIGNS:
        blob = " ".join(
            [sign["name"], sign.get("description", ""), " ".join(sign.get("keywords", []))]
        ).lower()
        if query in blob:
            matches.append(sign)
    return matches

@app.get("/signs/lookup")
async def lookup_sign(name: str = Query(...)):
    needle = name.strip().lower()
    for sign in SIGNS:
        if sign["name"].lower() == needle:
            return {"sign": sign}
    return {"sign": None}

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
    # Save messages dict (convert defaultdict to dict)
    save_json("messages.json", dict(MESSAGES))
    return {"ok": True}

@app.get("/history/{user_id}")
async def get_history(user_id: str):
    return JSONResponse(MESSAGES.get(user_id, []))

@app.delete("/history/{user_id}")
async def clear_history(user_id: str):
    MESSAGES[user_id] = []
    save_json("messages.json", dict(MESSAGES))
    return {"ok": True}

# -----------------------------------------------------------------------------
# Translation (stub)
# -----------------------------------------------------------------------------
@app.get("/translate")
async def translate(text: str = Query(""), lang: str = Query("en")):
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
    body: dict = Body(...),
):
    if not isinstance(body, dict) or "frames" not in body:
        return JSONResponse({"ok": False, "error": "Invalid body"}, status_code=400)
    CUSTOM_GESTURES[user_id].append({"name": name, "seq_json": body})
    save_json("gestures.json", dict(CUSTOM_GESTURES))
    return {"ok": True, "count": len(CUSTOM_GESTURES[user_id])}

# -----------------------------------------------------------------------------
# SOS
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
    save_json("sos.json", SOS_LOG)
    return {"ok": True, "saved": item}

# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True, "time": now_iso()}

