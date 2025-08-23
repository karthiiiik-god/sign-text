# main.py
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="SignCall Backend")

# --- CORS (allow everything for dev; tighten in prod) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],   # FIX: must be "*", not ""
    allow_headers=["*"],   # FIX: must be "*", not ""
)

# ===== In-memory stores (OK for demos; swap to DB in prod) =====
MESSAGES: Dict[str, List[dict]] = defaultdict(list)              # user_id -> [{content, emoji, timestamp}]
CUSTOM_GESTURES: Dict[str, List[dict]] = defaultdict(list)       # user_id -> [{name, seq_json}]
SIGNALING: Dict[str, Set[WebSocket]] = defaultdict(set)          # user_id -> websockets

# WebRTC signaling room: room -> {clientId: websocket}
ROOM_SOCKS: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
# Reverse map: websocket -> (room, clientId)
WS_META: Dict[WebSocket, Dict[str, str]] = {}

# ===== Helpers =====
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ===== Auth (demo) =====
@app.post("/login")
async def login(email: str = Query(...), password: str = Query(...)):
    # Demo auth: treat the email as user_id
    return {"user_id": email}

@app.post("/signup")
async def signup(email: str = Query(...), password: str = Query(...)):
    # Demo signup: no storage, just echo an id
    return {"user_id": email}

# ===== Chat & history =====
@app.post("/message")
async def post_message(
    user_id: str = Query(...),
    content: str = Query(""),
    emoji: str = Query(""),
    language: str = Query("en"),
):
    MESSAGES[user_id].append({
        "content": content, "emoji": emoji,
        "language": language, "timestamp": now_iso(),
    })
    return {"ok": True}

@app.get("/history/{user_id}")
async def get_history(user_id: str):
    return JSONResponse(MESSAGES.get(user_id, []))

@app.delete("/history/{user_id}")
async def clear_history(user_id: str):
    MESSAGES[user_id].clear()
    return {"ok": True}

# ===== Translation (demo stub) =====
@app.get("/translate")
async def translate(text: str = Query(""), lang: str = Query("en")):
    # Stub: just echo text; plug real translator here (e.g., gcloud/LibreTranslate)
    return {"translated": text}

# ===== Custom gesture endpoints =====
@app.get("/custom_gesture/samples")
async def list_gesture_samples(user_id: str = Query(...)):
    return JSONResponse(CUSTOM_GESTURES.get(user_id, []))

@app.post("/custom_gesture/save")
async def save_gesture_sample(
    user_id: str = Query(...),
    name: str = Query(...),
    sample_idx: int = Query(0),
    body: dict = None,
):
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Invalid body"}, status_code=400)
    CUSTOM_GESTURES[user_id].append({"name": name, "seq_json": body})
    return {"ok": True, "count": len(CUSTOM_GESTURES[user_id])}

# ===== WebSocket: user presence signaling (rings & accept/reject) =====
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
                payload = {"type": "incoming_call", "from": msg.get("from"), "room": msg.get("room")}
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
        # clean up
        if user_id and ws in SIGNALING.get(user_id, set()):
            SIGNALING[user_id].discard(ws)

# ===== WebSocket: WebRTC room signaling (native WebRTC, no PeerJS) =====
@app.websocket("/ws/room/{room_code}")
async def ws_room(ws: WebSocket, room_code: str):
    await ws.accept()
    client_id = None
    try:
        # Expect first message: {"type":"hello", "clientId": "...", "userId": "..."}
        hello_raw = await ws.receive_text()
        hello = json.loads(hello_raw)
        assert hello.get("type") == "hello" and hello.get("clientId")
        client_id = str(hello["clientId"])

        # Register
        ROOM_SOCKS[room_code][client_id] = ws
        WS_META[ws] = {"room": room_code, "clientId": client_id}

        # Send roster (others)
        others = [cid for cid in ROOM_SOCKS[room_code].keys() if cid != client_id]
        await ws.send_text(json.dumps({"type": "roster", "peers": others}))

        # Notify others that a new peer joined (optional)
        join_msg = json.dumps({"type": "peer_joined", "clientId": client_id})
        for cid, peer_ws in list(ROOM_SOCKS[room_code].items()):
            if cid == client_id:
                continue
            try:
                await peer_ws.send_text(join_msg)
            except Exception:
                # drop dead sockets
                ROOM_SOCKS[room_code].pop(cid, None)

        # Relay loop
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            # Relay WebRTC signals: {type:"signal", to:"clientId", from:"clientId", data:{...}}
            if msg.get("type") == "signal" and msg.get("to"):
                to_id = str(msg.get("to"))
                target = ROOM_SOCKS[room_code].get(to_id)
                if target:
                    try:
                        await target.send_text(json.dumps({
                            "type": "signal",
                            "from": client_id,
                            "data": msg.get("data", {}),
                        }))
                    except Exception:
                        ROOM_SOCKS[room_code].pop(to_id, None)
                continue

            # Optional pings
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        # Bad hello or parse error
        try:
            await ws.close(code=4000)
        except Exception:
            pass
    finally:
        meta = WS_META.pop(ws, None)
        if meta:
            room = meta["room"]
            cid = meta["clientId"]
            if room in ROOM_SOCKS and cid in ROOM_SOCKS[room]:
                ROOM_SOCKS[room].pop(cid, None)
                # Notify remaining peers
                left_msg = json.dumps({"type": "peer_left", "clientId": cid})
                for pid, pws in list(ROOM_SOCKS[room].items()):
                    try:
                        await pws.send_text(left_msg)
                    except Exception:
                        ROOM_SOCKS[room].pop(pid, None)
            if room in ROOM_SOCKS and not ROOM_SOCKS[room]:
                ROOM_SOCKS.pop(room, None)
