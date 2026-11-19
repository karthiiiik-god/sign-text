# app.py
import os
import json
import re

import requests
import streamlit as st

# ===================== PAGE CONFIG =====================
st.set_page_config(
    page_title="SignCall",
    page_icon="✌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===================== BACKEND URL =====================
BACKEND = os.getenv("BACKEND_URL")
if not BACKEND:
    try:
        BACKEND = st.secrets["BACKEND_URL"]
    except Exception:
        BACKEND = "http://127.0.0.1:8003"

EMOJI_MAP = {"Yes": "👍", "No": "👎", "Hello": "✌"}
EMAIL_RE  = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ===================== SESSION STATE ===================
st.session_state.setdefault("authenticated", False)
st.session_state.setdefault("user_id",       "")
st.session_state.setdefault("user_email",    "")
st.session_state.setdefault("teach_on",      False)
st.session_state.setdefault("auth_mode",     "Sign in")

# ===================== HELPERS =========================
def api_error_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return (response.text or "").strip() or "The server rejected the request."
    detail = data.get("detail", data.get("error"))
    if isinstance(detail, list):
        parts = [str(i.get("msg") or i) if isinstance(i, dict) else str(i) for i in detail]
        return "; ".join(parts) or "The server rejected the request."
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return "The server rejected the request."

def request_error_message(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Cannot reach the server. Make sure the backend is running on port 8003."
    if isinstance(exc, requests.exceptions.Timeout):
        return "The server took too long to respond. Try again."
    return "Something went wrong. Try again."

def validate_email(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if not cleaned:
        return "Enter your email address."
    if not EMAIL_RE.match(cleaned):
        return "Enter a valid email, like name@example.com."
    return ""

def sign_in(email: str, password: str) -> None:
    err = validate_email(email)
    if err:
        st.error(err); return
    if not (password or "").strip():
        st.error("Enter your password."); return
    try:
        r = requests.post(f"{BACKEND}/login",
                          json={"email": email.strip().lower(), "password": password},
                          timeout=15)
    except requests.RequestException as exc:
        st.error(request_error_message(exc)); return
    if not r.ok:
        st.error(api_error_message(r)); return
    uid = r.json().get("user_id")
    if not uid:
        st.error("The server did not return an account id."); return
    st.session_state.update(authenticated=True, user_id=uid, user_email=uid)
    st.rerun()

def create_account(email: str, password: str, confirm: str) -> None:
    err = validate_email(email)
    if err:
        st.error(err); return
    if not (password or "").strip():
        st.error("Choose a password."); return
    if len(password) < 6:
        st.error("Password must be at least 6 characters."); return
    if password != confirm:
        st.error("Passwords do not match."); return
    payload = {"email": email.strip().lower(), "password": password}
    try:
        r = requests.post(f"{BACKEND}/signup", json=payload, timeout=15)
    except requests.RequestException as exc:
        st.error(request_error_message(exc)); return
    if not r.ok:
        st.error(api_error_message(r)); return
    uid = r.json().get("user_id") or payload["email"]
    st.session_state.update(authenticated=True, user_id=uid, user_email=uid)
    st.rerun()

# ===================== GLOBAL STYLES ===================
st.markdown("""
<style>
/* ── Reset Streamlit defaults ── */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
.stApp { background: #f5f7fa !important; }

[data-testid="stHeader"]  { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1100px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e2e8f0 !important;
}
[data-testid="stSidebar"] * { color: #1e293b !important; }
[data-testid="stSidebar"] h2 {
    font-size: 11px !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #94a3b8 !important;
    margin-top: 1.4rem !important;
    margin-bottom: 0.4rem !important;
}
[data-testid="stSidebar"] hr { border-color: #e2e8f0 !important; }

/* ── Auth card ── */
.auth-wrap {
    max-width: 420px;
    margin: 0 auto;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 40px 36px 32px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.07);
}
.auth-logo {
    font-size: 36px;
    text-align: center;
    margin-bottom: 6px;
}
.auth-title {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    text-align: center;
    margin-bottom: 4px;
}
.auth-sub {
    font-size: 13px;
    color: #64748b;
    text-align: center;
    margin-bottom: 24px;
}

/* ── Inputs ── */
.stTextInput input {
    background: #f8fafc !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 8px !important;
    color: #0f172a !important;
    font-size: 14px !important;
    height: 44px !important;
}
.stTextInput input:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.12) !important;
    outline: none !important;
}
.stTextInput label {
    color: #374151 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
}

/* ── Buttons ── */
.stFormSubmitButton > button,
button[kind="primary"] {
    background: #2563eb !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    height: 44px !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    width: 100% !important;
    transition: background 0.15s;
}
.stFormSubmitButton > button:hover,
button[kind="primary"]:hover {
    background: #1d4ed8 !important;
}
button[kind="secondary"] {
    background: #ffffff !important;
    color: #374151 !important;
    border: 1px solid #d1d5db !important;
    border-radius: 8px !important;
    font-size: 14px !important;
}
button[kind="secondary"]:hover {
    background: #f1f5f9 !important;
}

/* ── Form container ── */
div[data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
}

/* ── Radio toggle (auth mode) ── */
div[role="radiogroup"] {
    display: flex;
    background: #f1f5f9;
    border-radius: 10px;
    padding: 3px;
    gap: 2px;
    margin-bottom: 20px;
}
div[role="radiogroup"] label {
    flex: 1;
    text-align: center;
    border-radius: 8px !important;
    padding: 7px 0 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #64748b !important;
    cursor: pointer;
    transition: background 0.15s;
}

/* ── Alerts ── */
div[data-testid="stAlert"] {
    border-radius: 8px !important;
    font-size: 13px !important;
}

/* ── Caption ── */
.stCaption p {
    color: #94a3b8 !important;
    font-size: 12px !important;
    text-align: center;
    margin-top: 10px;
}

/* ── Main page title ── */
h1 { color: #0f172a !important; font-size: 24px !important; font-weight: 700 !important; }

/* ── Section divider ── */
hr { border-color: #e2e8f0 !important; }
</style>
""", unsafe_allow_html=True)

# ===================== AUTH PAGE ======================
if not st.session_state.get("authenticated"):
    st.markdown("""<style>
        [data-testid="stSidebar"]              { display: none !important; }
        [data-testid="stSidebarCollapsedControl"] { display: none !important; }
        .block-container { padding-top: 3rem !important; max-width: 100% !important; }
    </style>""", unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        # Card open
        st.markdown('<div class="auth-wrap">', unsafe_allow_html=True)

        # Logo + title
        st.markdown('<div class="auth-logo">✌</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-title">SignCall</div>', unsafe_allow_html=True)

        # Mode toggle
        mode = st.radio(
            "auth_mode_toggle",
            ["Sign in", "Create account"],
            horizontal=True,
            key="auth_mode",
            label_visibility="collapsed",
        )

        if mode == "Sign in":
            st.markdown('<div class="auth-sub">Sign in to your account to continue.</div>',
                        unsafe_allow_html=True)
            with st.form("login_form", clear_on_submit=False):
                email    = st.text_input("Email address", placeholder="name@example.com", key="li_email")
                password = st.text_input("Password", type="password", placeholder="Your password", key="li_pw")
                submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if submitted:
                sign_in(email, password)
            st.caption("New here? Switch to **Create account** above.")

        else:
            st.markdown('<div class="auth-sub">Create a free account in seconds.</div>',
                        unsafe_allow_html=True)
            with st.form("signup_form", clear_on_submit=False):
                email    = st.text_input("Email address", placeholder="name@example.com",    key="su_email")
                password = st.text_input("Password",       type="password", placeholder="At least 6 characters", key="su_pw")
                confirm  = st.text_input("Confirm password", type="password", placeholder="Repeat your password",  key="su_pw2")
                submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if submitted:
                create_account(email, password, confirm)
            st.caption("Already have an account? Switch to **Sign in** above.")

        st.markdown('</div>', unsafe_allow_html=True)  # close .auth-wrap

    st.stop()

# ===================== SIDEBAR =========================
with st.sidebar:
    st.markdown("## Account")
    email_display = st.session_state.get("user_email") or st.session_state.get("user_id")
    st.markdown(f"**{email_display}**")
    if st.button("Log out", use_container_width=True):
        st.session_state.update(
            authenticated=False, user_id="", user_email="", teach_on=False
        )
        st.rerun()

    st.markdown("---")
    st.markdown("## 🌐 Languages")
    LANG_CHOICES = [
        ("ta","Tamil"), ("hi","Hindi"), ("te","Telugu"),  ("kn","Kannada"),
        ("ml","Malayalam"), ("mr","Marathi"), ("bn","Bengali"),
        ("gu","Gujarati"), ("pa","Punjabi"), ("ur","Urdu"), ("en","English"),
    ]
    selected_langs = st.multiselect(
        "Translate detected signs to:",
        options=[c[0] for c in LANG_CHOICES],
        default=["ta", "hi"],
        format_func=lambda x: dict(LANG_CHOICES)[x],
    )
    if "en" not in selected_langs:
        selected_langs.append("en")

    st.markdown("## 🔊 Audio")
    tts_rate  = st.slider("Voice speed",  0.5, 2.0, 1.0, 0.1)
    tts_pitch = st.slider("Voice pitch",  0.0, 2.0, 1.0, 0.1)

# ===================== MAIN HEADER ====================
st.markdown("## ✌ SignCall — Sign Language Detector")
st.markdown("---")

section = st.segmented_control(
    "section",
    options=["Live Detector", "Teach New Sign", "Sign Dictionary"],
    default="Live Detector",
    key="main_section",
    label_visibility="collapsed",
)
if section is None:
    section = "Live Detector"

st.markdown("")   # breathing room

# ===================== LIVE DETECTOR ==================
if section == "Live Detector":
    _backend_js  = json.dumps(BACKEND)
    _user_id_js  = json.dumps(st.session_state["user_id"])
    _tts_rate    = float(tts_rate)
    _tts_pitch   = float(tts_pitch)
    _langs_js    = json.dumps(selected_langs)

    st.components.v1.html(f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f5f7fa;
    color: #1e293b;
    padding: 12px;
  }}

  /* Layout */
  .main-grid {{
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }}

  /* Camera card */
  .cam-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 14px;
    width: 360px;
    min-width: 280px;
  }}
  .cam-card h3 {{
    font-size: 13px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 10px;
  }}
  video {{
    width: 100%;
    height: 220px;
    background: #0f172a;
    border-radius: 8px;
    object-fit: cover;
    display: block;
  }}

  /* Result card */
  .result-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 14px;
    flex: 1;
    min-width: 240px;
  }}
  .result-card h3 {{
    font-size: 13px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 10px;
  }}
  #localCap {{
    font-size: 28px;
    font-weight: 700;
    color: #0f172a;
    min-height: 40px;
  }}
  #localTrans {{
    font-size: 13px;
    color: #475569;
    margin-top: 8px;
    line-height: 1.6;
  }}
  #signInfo {{
    font-size: 13px;
    color: #475569;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid #f1f5f9;
  }}
  img.media {{
    max-width: 100%;
    border-radius: 8px;
    margin-top: 6px;
  }}

  /* Buttons */
  .btn-row {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 14px;
  }}
  .btn {{
    padding: 7px 14px;
    border-radius: 7px;
    border: 1px solid #d1d5db;
    background: #ffffff;
    color: #374151;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }}
  .btn:hover {{ background: #f1f5f9; border-color: #94a3b8; }}
  .btn.primary {{
    background: #2563eb;
    color: #fff;
    border-color: #2563eb;
  }}
  .btn.primary:hover {{ background: #1d4ed8; border-color: #1d4ed8; }}
  .btn.danger {{ border-color: #fca5a5; color: #dc2626; }}
  .btn.danger:hover {{ background: #fef2f2; }}

  /* Status + chips */
  .status-bar {{
    margin-top: 10px;
    font-size: 12px;
    color: #64748b;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 6px 10px;
  }}
  .chip-label {{
    font-size: 12px;
    color: #94a3b8;
    margin-top: 10px;
    margin-bottom: 4px;
  }}
  .chips {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }}
  .chip {{
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 500;
  }}
</style>
</head>
<body>

<div class="main-grid">
  <!-- Camera -->
  <div class="cam-card">
    <h3>📷 Camera Feed</h3>
    <video id="localVideo" autoplay playsinline muted></video>
    <div class="btn-row">
      <button class="btn primary" id="startCam">Start Camera</button>
      <button class="btn danger"  id="stopCam">Stop</button>
      <button class="btn primary" id="startGest">Start Gestures</button>
      <button class="btn danger"  id="stopGest">Stop</button>
      <button class="btn"         id="refreshLib">↺ Refresh</button>
    </div>
    <div class="status-bar" id="status">Status: idle</div>
    <div class="chip-label">Custom gestures loaded:</div>
    <div class="chips" id="customList"></div>
  </div>

  <!-- Result -->
  <div class="result-card">
    <h3>🖐 Detected Sign</h3>
    <div id="localCap">—</div>
    <div id="localTrans"></div>
    <div id="signInfo"></div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js"></script>
<script>
const BACKEND   = {_backend_js};
const USER_ID   = {_user_id_js};
const TTS_RATE  = {_tts_rate};
const TTS_PITCH = {_tts_pitch};
const LANGS     = {_langs_js};

const statusEl   = document.getElementById('status');
const localVideo = document.getElementById('localVideo');
const localCap   = document.getElementById('localCap');
const localTrans = document.getElementById('localTrans');
const signInfo   = document.getElementById('signInfo');
const customList = document.getElementById('customList');

let localStream = null, GESTURE_LIB = [], WIN = [], customOn = false, cooldownUntil = 0, camera = null;

function setStatus(t) {{ statusEl.textContent = "Status: " + t; }}

async function apiSave(content, emoji) {{
  try {{
    await fetch(BACKEND+'/message?user_id='+encodeURIComponent(USER_ID)
      +'&content='+encodeURIComponent(content)+'&emoji='+encodeURIComponent(emoji)+'&language=en',
      {{method:'POST'}});
  }} catch(e) {{}}
}}

async function tr(text, lang) {{
  try {{
    const r = await fetch(BACKEND+'/translate?text='+encodeURIComponent(text)+'&lang='+lang);
    if (!r.ok) return ""; return (await r.json()).translated || "";
  }} catch(e) {{ return ""; }}
}}

async function fetchSign(name) {{
  try {{
    const r = await fetch(BACKEND+'/signs/lookup?name='+encodeURIComponent(name));
    if (!r.ok) return null; return (await r.json()).sign || null;
  }} catch(e) {{ return null; }}
}}

function speak(text) {{
  try {{
    const u = new SpeechSynthesisUtterance(text);
    u.lang="en-US"; u.rate=TTS_RATE; u.pitch=TTS_PITCH;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }} catch(e) {{}}
}}

function renderChips() {{
  customList.innerHTML="";
  if (!GESTURE_LIB.length) {{
    customList.innerHTML='<span class="chip" style="background:#f1f5f9;color:#94a3b8;border-color:#e2e8f0">None yet</span>'; return;
  }}
  [...new Set(GESTURE_LIB.map(g=>g.name))].forEach(n=>{{
    const c=document.createElement('span'); c.className='chip'; c.textContent=n; customList.appendChild(c);
  }});
}}

function meanVec(frames) {{
  const d=63, out=new Float32Array(d);
  frames.forEach(f=>{{ for(let j=0;j<d;j++) out[j]+=f[j]; }});
  const inv=1/Math.max(frames.length,1);
  for(let j=0;j<d;j++) out[j]*=inv; return out;
}}
function cosine(a,b) {{
  let dot=0,na=0,nb=0;
  for(let i=0;i<a.length;i++){{dot+=a[i]*b[i];na+=a[i]*a[i];nb+=b[i]*b[i];}}
  return dot/(Math.sqrt(na)*Math.sqrt(nb)+1e-9);
}}

async function loadGestureLibrary() {{
  try {{
    const r=await fetch(BACKEND+'/custom_gesture/samples?user_id='+encodeURIComponent(USER_ID));
    if(!r.ok) throw new Error();
    const rows=await r.json(), lib=[];
    for(const row of rows) {{
      const name=row.name||"custom";
      const frames=(row.seq_json?.frames||[]).map(fr=>Float32Array.from(fr.flat?fr.flat():fr));
      lib.push({{name,vecs:[meanVec(frames)]}});
    }}
    const byName={{}};
    lib.forEach(g=>{{ if(!byName[g.name]) byName[g.name]={{name:g.name,vecs:[]}}; byName[g.name].vecs.push(...g.vecs); }});
    GESTURE_LIB=Object.values(byName); renderChips();
    customOn=GESTURE_LIB.length>0;
    setStatus(customOn?"Gestures ON ("+GESTURE_LIB.length+" custom)":"Gestures ON");
  }} catch(e) {{ GESTURE_LIB=[]; renderChips(); }}
}}

function normalize(pts) {{
  const base=pts[0];
  const s=pts.map(p=>[p[0]-base[0],p[1]-base[1],p[2]-base[2]]);
  let m=0; for(let i=1;i<s.length;i++) m+=Math.hypot(s[i][0],s[i][1],s[i][2]);
  m=Math.max(m/(s.length-1),1e-6); return s.map(p=>[p[0]/m,p[1]/m,p[2]/m]);
}}
function flatten63(n) {{
  const o=new Float32Array(63); let k=0;
  for(let i=0;i<21;i++){{o[k++]=n[i][0];o[k++]=n[i][1];o[k++]=n[i][2];}} return o;
}}

async function broadcastCaption(text, emoji) {{
  localCap.textContent = text + (emoji?" "+emoji:"");
  apiSave(text, emoji);
  const lines=[];
  for(const L of LANGS) {{ const t=await tr(text,L); lines.push("<b>"+L.toUpperCase()+"</b>: "+t); }}
  localTrans.innerHTML=lines.join("&nbsp;&nbsp;·&nbsp;&nbsp;");
  const info=await fetchSign(text);
  if(info) {{
    signInfo.innerHTML="<b>"+info.name+"</b> "+(info.emoji||"")+"<br/>"+(info.description||"")
      +(info.media?'<br/><img class="media" src="'+info.media+'"/>':'');
  }} else {{ signInfo.innerHTML=""; }}
  speak(text);
}}

function tryCustom() {{
  if(!customOn||Date.now()<cooldownUntil||WIN.length<36) return;
  const cur=meanVec(WIN); let best="",score=-1;
  for(const g of GESTURE_LIB) for(const v of g.vecs) {{
    const s=cosine(cur,v); if(s>score){{score=s;best=g.name;}}
  }}
  if(score>=0.92){{ broadcastCaption(best,"🖐"); cooldownUntil=Date.now()+1500; WIN=[]; }}
}}

const hands=new Hands({{locateFile:f=>'https://cdn.jsdelivr.net/npm/@mediapipe/hands/'+f}});
hands.setOptions({{maxNumHands:1,modelComplexity:1,minDetectionConfidence:0.7,minTrackingConfidence:0.7}});
hands.onResults(results=>{{
  if(!results.multiHandLandmarks?.length) return;
  const lm=results.multiHandLandmarks[0];
  const ext=(t,p)=>lm[t].y<lm[p].y, fold=(t,p)=>lm[t].y>lm[p].y;
  const iE=ext(8,6),mE=ext(12,10),rF=fold(16,14),pF=fold(20,18);
  if(ext(4,2)&&rF&&pF&&!iE&&!mE)  {{broadcastCaption("Yes","👍");return;}}
  if(fold(4,2)&&rF&&pF&&!iE&&!mE) {{broadcastCaption("No","👎");return;}}
  if(iE&&mE&&rF&&pF&&Math.abs(lm[8].x-lm[12].x)>0.05) {{broadcastCaption("Hello","✌");return;}}
  const f63=flatten63(normalize(lm.map(p=>[p.x,p.y,p.z])));
  WIN.push(Array.from(f63)); if(WIN.length>36) WIN.shift();
  tryCustom();
}});

document.getElementById('startCam').onclick = async ()=>{{
  localStream=await navigator.mediaDevices.getUserMedia({{video:true,audio:false}});
  localVideo.srcObject=localStream; setStatus("Camera ON");
}};
document.getElementById('stopCam').onclick = ()=>{{
  if(localStream){{localStream.getTracks().forEach(t=>t.stop());localStream=null;localVideo.srcObject=null;}}
  setStatus("Camera OFF");
}};
document.getElementById('startGest').onclick = async ()=>{{
  if(!localStream){{setStatus("Start the camera first.");return;}}
  await loadGestureLibrary();
  const vg=document.createElement('video'); vg.srcObject=localStream; await vg.play();
  camera=new window.Camera(vg,{{onFrame:async()=>{{await hands.send({{image:vg}});}},width:320,height:240}});
  camera.start();
}};
document.getElementById('stopGest').onclick = ()=>{{
  try{{camera.stop();}}catch(_){{}} customOn=false; WIN=[]; setStatus("Gestures OFF");
}};
document.getElementById('refreshLib').onclick = async ()=>{{ await loadGestureLibrary(); }};

renderChips();
</script>
</body>
</html>
""", height=560, scrolling=False)


# ===================== TEACH NEW SIGN =================
elif section == "Teach New Sign":
    st.markdown("### Teach a New Sign")
    st.markdown("Record your own hand gesture and give it a name. The detector will recognise it next time.")
    st.markdown("---")

    c1, c2 = st.columns([2, 1])
    with c1:
        teach_name = st.text_input("Sign name", placeholder="e.g. Amma, Bus stop, Thank you", key="teach_name")
    with c2:
        teach_reps = st.number_input("Samples to record", min_value=5, max_value=20, value=8, key="teach_reps")

    st.caption("Hold your sign steady for 1–2 seconds per sample. The camera captures ~36 frames automatically.")

    col_a, col_b, _ = st.columns([1, 1, 2])
    if col_a.button("▶ Start Recording", type="primary", use_container_width=True):
        if teach_name.strip():
            st.session_state["teach_on"] = True
        else:
            st.warning("Enter a sign name first.")
    if col_b.button("⏹ Stop", use_container_width=True):
        st.session_state["teach_on"] = False

    if st.session_state.get("teach_on"):
        uid_js     = json.dumps(st.session_state["user_id"])
        name_js    = json.dumps(teach_name.strip())
        reps_js    = int(teach_reps)
        backend_js = json.dumps(BACKEND)

        st.components.v1.html(f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f5f7fa; color:#1e293b; padding:12px; }}
  .wrap {{ background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:16px; }}
  .row  {{ display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap; }}
  video {{ width:300px; height:220px; background:#0f172a; border-radius:8px; object-fit:cover; display:block; }}
  .info {{ flex:1; min-width:200px; }}
  .info h3 {{ font-size:14px; font-weight:600; margin-bottom:8px; color:#0f172a; }}
  .info ol {{ padding-left:18px; font-size:13px; color:#475569; line-height:1.8; }}
  #msg {{ margin-top:12px; font-size:13px; font-weight:600; padding:8px 12px; border-radius:7px; background:#fefce8; color:#854d0e; border:1px solid #fde68a; }}
  #msg.ok  {{ background:#f0fdf4; color:#166534; border-color:#bbf7d0; }}
  #msg.err {{ background:#fef2f2; color:#dc2626; border-color:#fecaca; }}
  .progress-bar-wrap {{ margin-top:14px; background:#e2e8f0; border-radius:999px; height:8px; overflow:hidden; }}
  .progress-bar {{ height:8px; background:#2563eb; border-radius:999px; width:0%; transition:width 0.3s; }}
  .progress-label {{ font-size:12px; color:#64748b; margin-top:6px; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js"></script>
</head>
<body>
<div class="wrap">
  <div class="row">
    <video id="cam" autoplay playsinline muted></video>
    <div class="info">
      <h3>Recording: <em>{teach_name}</em></h3>
      <ol>
        <li>Show your hand to the camera.</li>
        <li>Hold the <strong>{teach_name}</strong> sign steady for ~1–2 seconds.</li>
        <li>Repeat until all {reps_js} samples are captured.</li>
      </ol>
      <div id="msg">Preparing camera &amp; model…</div>
      <div class="progress-bar-wrap">
        <div class="progress-bar" id="bar"></div>
      </div>
      <div class="progress-label" id="prog">0 / {reps_js} samples</div>
    </div>
  </div>
</div>
<script>
const BACKEND={backend_js}, USER_ID={uid_js}, NAME={name_js}, TARGET={reps_js};
let teaching=true, count=0, frames=[], camera=null;

function setMsg(t,cls='') {{
  const e=document.getElementById('msg'); e.textContent=t; e.className=cls;
}}
function setProgress(n,t) {{
  document.getElementById('bar').style.width=(n/t*100)+'%';
  document.getElementById('prog').textContent=n+' / '+t+' samples';
}}

function normalize(pts) {{
  const b=pts[0], s=pts.map(p=>[p[0]-b[0],p[1]-b[1],p[2]-b[2]]);
  let m=0; for(let i=1;i<s.length;i++) m+=Math.hypot(s[i][0],s[i][1],s[i][2]);
  m=Math.max(m/(s.length-1),1e-6); return s.map(p=>[p[0]/m,p[1]/m,p[2]/m]);
}}
async function saveSample(idx,seq) {{
  try {{
    const r=await fetch(BACKEND+'/custom_gesture/save?user_id='+encodeURIComponent(USER_ID)
      +'&name='+encodeURIComponent(NAME)+'&sample_idx='+idx,
      {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{frames:seq}})}});
    return r.ok;
  }} catch(e){{return false;}}
}}
const hands=new Hands({{locateFile:f=>'https://cdn.jsdelivr.net/npm/@mediapipe/hands/'+f}});
hands.setOptions({{maxNumHands:1,modelComplexity:1,minDetectionConfidence:0.7,minTrackingConfidence:0.7}});
hands.onResults(async res=>{{
  if(!teaching) return;
  if(!res.multiHandLandmarks?.length) {{ setMsg("Show your hand to the camera and hold the sign steady…"); return; }}
  const lm=res.multiHandLandmarks[0];
  frames.push(normalize(lm.map(p=>[p.x,p.y,p.z])).flat());
  if(frames.length>=36) {{
    const seq=frames.slice(0,36); frames=[];
    count++; setProgress(count,TARGET);
    setMsg("Sample "+count+" captured ✓","ok");
    const ok=await saveSample(count,seq);
    if(!ok) setMsg("Save failed — check the backend.","err");
    if(count>=TARGET) {{
      setMsg("All "+TARGET+" samples saved! You can close this section.","ok");
      teaching=false;
      try{{camera.stop();}}catch(_){{}}
      try{{document.getElementById('cam').srcObject?.getTracks().forEach(t=>t.stop());}}catch(_){{}}
    }}
  }}
}});
(async()=>{{
  try {{
    const v=document.getElementById('cam');
    const s=await navigator.mediaDevices.getUserMedia({{video:{{width:300,height:220}}}});
    v.srcObject=s; await v.play();
    camera=new Camera(v,{{onFrame:async()=>{{await hands.send({{image:v}});}},width:300,height:220}});
    await camera.start();
    setMsg("Camera ready — hold your sign steady.","ok");
  }} catch(e) {{
    setMsg("Camera permission denied. Allow access and try again.","err");
  }}
}})();
</script>
</body>
</html>
""", height=360, scrolling=False)

    else:
        st.info("Enter a sign name above and click **▶ Start Recording** to begin.")


# ===================== SIGN DICTIONARY ================
elif section == "Sign Dictionary":
    st.markdown("### Sign Dictionary")
    st.markdown("Browse or search the built-in sign library.")
    st.markdown("---")

    q = st.text_input("🔍 Search by name or keyword", placeholder="e.g. hello, yes, no …", key="dict_q")

    try:
        r = requests.get(f"{BACKEND}/signs", params={"q": q}, timeout=10)
        items = r.json() if r.ok else []
        if not r.ok:
            st.error(api_error_message(r))
    except requests.RequestException as exc:
        st.error(request_error_message(exc))
        items = []

    if not items:
        st.info("No signs found. Try a different search term." if q else "No signs in the library yet.")
    else:
        cols = st.columns(3)
        for i, s in enumerate(items):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"### {s.get('emoji','')} {s.get('name','')}")
                    if s.get("media"):
                        st.image(s["media"], use_container_width=True)
                    if s.get("description"):
                        st.markdown(s["description"])
                    if s.get("keywords"):
                        kw = " · ".join(s["keywords"])
                        st.caption(f"Keywords: {kw}")
