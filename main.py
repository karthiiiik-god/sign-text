# main.py
import os
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title="SignCall Backend", version="1.0.0")

# CORS (dev-friendly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=[""],  # must be "" (not empty string)
    allow_headers=[""],  # must be "" (not empty string)
)

# -----------------------------------------------------------------------------
# In-memory stores (OK for demos; use a DB in production)
# -----------------------------------------------------------------------------
MESSAGES: Dict[str, List[dict]] = defaultdict(list)              # user_id -> [{content, emoji, timestamp}]
CUSTOM_GESTURES: Dict[str, List[dict]] = defaultdict(list)       # user_id -> [{name, seq_json}]
SIGNALING: Dict[str, Set[WebSocket]] = defaultdict(set)          # user_id -> websockets
ROOM_PEERS: Dict[str, Dict[WebSocket, str]] = defaultdict(dict)  # room -> {websocket: peerId}

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class GestureSample(BaseModel):
    # Expecting 36 frames; each frame is 63 floats (21 landmarks * x,y,z)
    # We accept any length to keep it flexible.
    frames: List[List[float]]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def send_peers_snapshot(room_code: str) -> None:
    """Send the current peer list to everyone in the room."""
    peers_map = ROOM_PEERS.get(room_code, {})
    if not peers_map:
        return
    peer_list = list(peers_map.values())
    payload = json.dumps({"type": "peers", "peers": peer_list})
    # Iterate on a copy to avoid size-change during loop
    for ws in list(peers_map.keys()):
        try:
            await ws.send_text(payload)
        except Exception:
            # Drop broken sockets
            ROOM_PEERS[room_code].pop(ws, None)

# -----------------------------------------------------------------------------
# Health / root
# -----------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"ok": True, "service": "SignCall Backend"}

@app.get("/health")
async def health():
    return {"ok": True, "time": now_iso()}

# -----------------------------------------------------------------------------
# Auth (demo stubs)
# -----------------------------------------------------------------------------
@app.post("/login")
async def login(email: str = Query(...), password: str = Query(...)):
    # Demo: treat the email as user_id
    return {"user_id": email}

@app.post("/signup")
async def signup(email: str = Query(...), password: str = Query(...)):
    # Demo: just echo an id
    return {"user_id": email}

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
        {"content": content, "emoji": emoji, "language": language, "timestamp": now_iso()}
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
# Translation (demo stub)
# -----------------------------------------------------------------------------
@app.get("/translate")
async def translate(text: str = Query(""), lang: str = Query("en")):
    # Stub: just echo text
    return {"translated": text}

# -----------------------------------------------------------------------------
# Custom gestures
# -----------------------------------------------------------------------------
@app.get("/custom_gesture/samples")
async def list_gesture_samples(user_id: str = Query(...)):
    return JSONResponse(CUSTOM_GESTURES.get(user_id, []))

@app.post("/custom_gesture/save")
async def save_gesture_sample(
    user_id: str = Query(...),
    name: str = Query(...),
    sample_idx: int = Query(0),
    body: GestureSample = Body(...),
):
    # Store raw sequence to keep things flexible; client can decide shape
    CUSTOM_GESTURES[user_id].append({"name": name, "seq_json": body.dict()})
    return {"ok": True, "count": len(CUSTOM_GESTURES[user_id])}

# -----------------------------------------------------------------------------
# WebSocket: signaling (rings & accept/reject)
# -----------------------------------------------------------------------------
@app.websocket("/ws/signaling")
async def ws_signaling(ws: WebSocket):
    await ws.accept()
    user_id = None
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # Initial hello
            if msg.get("type") == "presence_hello":
                user_id = msg.get("userId") or "anon"
                SIGNALING[user_id].add(ws)
                continue

            # Caller -> ring
            if msg.get("type") == "ring":
                to = msg.get("to")
                payload = {
                    "type": "incoming_call",
                    "from": msg.get("from"),
                    "room": msg.get("room"),
                }
                for peer_ws in list(SIGNALING.get(to, set())):
                    try:
                        await peer_ws.send_text(json.dumps(payload))
                    except Exception:
                        SIGNALING[to].discard(peer_ws)
                continue

            # Callee -> accept / reject
            if msg.get("type") in ("call_accept", "call_reject"):
                to = msg.get("to")  # original caller
                event = "call_accepted" if msg["type"] == "call_accept" else "call_rejected"
                payload = {
                    "type": event,
                    "from": msg.get("from"),
                    "room": msg.get("room"),
                }
                for peer_ws in list(SIGNALING.get(to, set())):
                    try:
                        await peer_ws.send_text(json.dumps(payload))
                    except Exception:
                        SIGNALING[to].discard(peer_ws)
                continue
    except WebSocketDisconnect:
        pass
    finally:
        if user_id and ws in SIGNALING.get(user_id, set()):
            SIGNALING[user_id].discard(ws)

# -----------------------------------------------------------------------------
# WebSocket: room discovery (PeerJS IDs list)
# -----------------------------------------------------------------------------
@app.websocket("/ws/room/{room_code}")
async def ws_room(ws: WebSocket, room_code: str):
    await ws.accept()
    try:
        # Expect first message: {"type":"hello", "peerId": "...", "userId": "..."}
        hello_raw = await ws.receive_text()
        hello_msg = json.loads(hello_raw)
        if hello_msg.get("type") != "hello" or not hello_msg.get("peerId"):
            await ws.close(code=4000)
            return
    except Exception:
        await ws.close(code=4000)
        return

    peer_id = hello_msg["peerId"]
    ROOM_PEERS[room_code][ws] = peer_id

    # Broadcast full peer list to everyone (this also informs the joiner)
    await send_peers_snapshot(room_code)

    try:
        while True:
            # Keep-alive; ignore arbitrary text from clients
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # Remove from room and broadcast updated list
        ROOM_PEERS[room_code].pop(ws, None)
        if ROOM_PEERS.get(room_code):
            await send_peers_snapshot(room_code)
        else:
            ROOM_PEERS.pop(room_code, None)

# -----------------------------------------------------------------------------
# Local dev runner
# -----------------------------------------------------------------------------
if __name__ == "_main_":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8003")),
        reload=True,
    )