# main.py
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Set

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="SignCall Backend")

# -------- CORS (allow everything for dev; tighten in prod) --------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- In-memory stores (demo) --------
MESSAGES: Dict[str, List[dict]] = defaultdict(list)              # user_id -> [{content, emoji, timestamp}]
CUSTOM_GESTURES: Dict[str, List[dict]] = defaultdict(list)       # user_id -> [{name, seq_json}]
SIGNALING: Dict[str, Set[WebSocket]] = defaultdict(set)          # user_id -> websockets
ROOM_PEERS: Dict[str, Dict[WebSocket, str]] = defaultdict(dict)  # room -> {websocket: peerId}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# -------- Models --------
class GestureSample(BaseModel):
    # 36 frames, each a list of 63 floats (21 landmarks * x,y,z)
    frames: List[List[float]] = Field(default_factory=list)

# -------- Health --------
@app.get("/")
async def root():
    return {"ok": True, "service": "SignCall Backend", "time": now_iso()}

# -------- Auth (demo) --------
@app.post("/login")
async def login(email: str = Query(...), password: str = Query(...)):
    return {"user_id": email}

@app.post("/signup")
async def signup(email: str = Query(...), password: str = Query(...)):
    return {"user_id": email}

# -------- Chat & history --------
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

# -------- Translation (stub) --------
@app.get("/translate")
async def translate(text: str = Query(""), lang: str = Query("en")):
    # Stub: echo back. Replace with real translator if needed.
    return {"translated": text}

# -------- Custom gesture endpoints --------
@app.get("/custom_gesture/samples")
async def list_gesture_samples(user_id: str = Query(...)):
    return JSONResponse(CUSTOM_GESTURES.get(user_id, []))

@app.post("/custom_gesture/save")
async def save_gesture_sample(
    user_id: str = Query(...),
    name: str = Query(...),
    sample_idx: int = Query(0),
    sample: GestureSample = Body(...),
):
    if not sample.frames or not isinstance(sample.frames, list):
        return JSONResponse({"ok": False, "error": "frames missing"}, status_code=400)
    # (Optionally validate: len(sample.frames) == 36 and len(frame)==63)
    CUSTOM_GESTURES[user_id].append({"name": name, "seq_json": sample.dict()})
    return {"ok": True, "count": len(CUSTOM_GESTURES[user_id])}

# -------- WebSocket: signaling (ring / accept / reject) --------
@app.websocket("/ws/signaling")
async def ws_signaling(ws: WebSocket):
    await ws.accept()
    user_id = None
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "presence_hello":
                user_id = msg.get("userId") or "anon"
                SIGNALING[user_id].add(ws)
                await ws.send_text(json.dumps({"type": "presence_ack", "userId": user_id}))
                continue

            if msg.get("type") == "ring":
                to = msg.get("to")
                payload = {"type": "incoming_call", "from": msg.get("from"), "room": msg.get("room")}
                for peer_ws in list(SIGNALING.get(to, set())):
                    try:
                        await peer_ws.send_text(json.dumps(payload))
                    except Exception:
                        SIGNALING[to].discard(peer_ws)
                continue

            if msg.get("type") in ("call_accept", "call_reject"):
                to = msg.get("to")
                event = "call_accepted" if msg["type"] == "call_accept" else "call_rejected"
                payload = {"type": event, "from": msg.get("from"), "room": msg.get("room")}
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
            if not SIGNALING[user_id]:
                SIGNALING.pop(user_id, None)

# -------- WebSocket: room discovery (PeerJS ids) --------
@app.websocket("/ws/room/{room_code}")
async def ws_room(ws: WebSocket, room_code: str):
    await ws.accept()
    try:
        hello = await ws.receive_text()
        hello_msg = json.loads(hello)
        if not (hello_msg.get("type") == "hello" and hello_msg.get("peerId")):
            await ws.close(code=4000)
            return
    except Exception:
        await ws.close(code=4000)
        return

    peer_id = hello_msg["peerId"]
    ROOM_PEERS[room_code][ws] = peer_id

    # send existing peers
    try:
        others = [p for w, p in ROOM_PEERS[room_code].items() if w is not ws]
        await ws.send_text(json.dumps({"type": "peers", "peers": others}))
    except Exception:
        pass

    # notify others (optional for your UI)
    join_msg = json.dumps({"type": "peer_joined", "peerId": peer_id})
    for w in list(ROOM_PEERS[room_code].keys()):
        if w is not ws:
            try:
                await w.send_text(join_msg)
            except Exception:
                ROOM_PEERS[room_code].pop(w, None)

    try:
        while True:
            _ = await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        pass
    finally:
        ROOM_PEERS[room_code].pop(ws, None)
        if not ROOM_PEERS[room_code]:
            ROOM_PEERS.pop(room_code, None)
