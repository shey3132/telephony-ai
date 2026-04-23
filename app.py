import os
import base64
import requests
import logging
import re
import time
from urllib.parse import quote
from flask import Flask, request
from threading import Lock

# הגדרת לוגים מתוקנת - ללא KeyError
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# קונפיגורציה
API_KEY = os.environ.get("GEMINI_KEY")
YM_USER = os.environ.get("YM_USER")
YM_PASS = os.environ.get("YM_PASS")

# הגדרות ביצועים ו-Thread Safety
TOTAL_BUDGET = 27.0  
LAST_CALLS = {}
CACHE = {}
data_lock = Lock()
session = requests.Session()
session.headers.update({"User-Agent": "AI-Telephony-Gateway/1.2"})

def normalize_text(text):
    if not text: return ""
    # Whitelist מורחב התומך בפיסוק הקריינות של ימות המשיח
    cleaned = re.sub(r'[^א-תa-zA-Z0-9\s.,?!:\-()"]', '', text)
    return re.sub(r'\s+', ' ', cleaned)[:350].strip()

def get_mime_type(path):
    p = path.lower()
    if p.endswith(".mp3"): return "audio/mpeg"
    if p.endswith(".gsm"): return "audio/gsm"
    if p.endswith(".amr"): return "audio/amr"
    return "audio/wav"

@app.route("/chat", methods=["GET", "POST"])
def chat():
    start_time = time.time()
    ip = request.remote_addr
    
    # 1. Rate Limit & Cache Check (Thread Safe)
    with data_lock:
        now = time.time()
        if ip in LAST_CALLS and now - LAST_CALLS[ip] < 0.6:
            return "id_list_message=t-נא להמתין בין בקשות&goto=.", 429
        LAST_CALLS[ip] = now
        
        # ניקוי זכרון תקופתי ל-Dicts
        if len(LAST_CALLS) > 1000: LAST_CALLS.clear()
        if len(CACHE) > 500: CACHE.clear()

    try:
        if request.values.get("hangup") == "yes": return "OK"

        audio_path = request.values.get("audio_file")
        if not audio_path:
            return "read=t-נא לומר שאלה לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        clean_path = audio_path.lstrip("/")
        
        # בדיקת Cache
        if clean_path in CACHE:
            logger.info(f"Cache Hit: {clean_path}")
            return CACHE[clean_path]

        if not all([API_KEY, YM_USER, YM_PASS]):
            return "id_list_message=t-שגיאת הגדרות שרת&goto=."

        # 2. הורדת קובץ
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={quote(YM_USER)}&password={quote(YM_PASS)}&path={quote(clean_path)}"
        
        audio_content = None
        for attempt in range(2):
            if time.time() - start_time > TOTAL_BUDGET - 12: break
            try:
                res = session.get(audio_url, timeout=10)
                res.raise_for_status()
                # בדיקת שתיקה (Silence Detection) בסיסית
                if len(res.content) < 600 or res.content.count(b'\x00') / len(res.content) > 0.9:
                    return "id_list_message=t-לא נשמע קול בהקלטה&goto=."
                audio_content = res.content
                break
            except Exception as e:
                logger.warning(f"Download Error: {e}")
                time.sleep(0.5)

        if not audio_content:
            return "id_list_message=t-תקלה בהורדת השמע&goto=."

        # 3. AI Processing
        mime_type = get_mime_type(clean_path)
        base64_audio = base64.b64encode(audio_content).decode("utf-8")
        
        if len(base64_audio) > 8_000_000: # הגנה על Payload
            return "id_list_message=t-הקלטה ארוכה מדי&goto=."

        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        payload = {
            "contents": [{"parts": [
                {"text": "תמלל וענה בקצרה בעברית. אם אין דיבור, ענה: לא שמעתי."},
                {"inline_data": {"mime_type": mime_type, "data": base64_audio}}
            ]}]
        }

        ai_text = None
        for attempt in range(2):
            # בדיקת Budget לפני שליחה ל-AI
            elapsed = time.time() - start_time
            if elapsed > TOTAL_BUDGET - 6: break
            
            try:
                res_ai = session.post(gemini_url, json=payload, timeout=min(20, TOTAL_BUDGET - elapsed))
                
                if res_ai.status_code == 429:
                    time.sleep(2)
                    continue
                
                res_ai.raise_for_status()
                data = res_ai.json()
                
                # Safe Parsing
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        ai_text = parts[0].get("text", "").strip()
                        if ai_text: break
                
                time.sleep(1)
            except Exception as e:
                logger.error(f"AI Attempt {attempt+1} Failed: {e}")

        # 4. Response & Cache
        if not ai_text or "לא שמעתי" in ai_text:
            return "id_list_message=t-לא הצלחתי להבין, נסה שנית&goto=."

        final_response = normalize_text(ai_text)
        response_string = f"id_list_message=t-{final_response}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"
        
        with data_lock:
            CACHE[clean_path] = response_string
            
        logger.info(f"Success | {round(time.time()-start_time, 2)}s | Res: {final_response[:30]}...")
        return response_string

    except Exception as e:
        logger.error(f"Critical Crash: {e}")
        return "id_list_message=t-אירעה שגיאה, נסה שוב מאוחר יותר&goto=."

@app.route("/")
def health():
    return "Gateway Active", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
