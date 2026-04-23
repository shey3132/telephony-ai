import os
import base64
import requests
import logging
import re
import time
from urllib.parse import quote
from flask import Flask, request
from threading import Lock

# לוגים מסודרים
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# קונפיגורציה
API_KEY = os.environ.get("GEMINI_KEY")
YM_USER = os.environ.get("YM_USER")
YM_PASS = os.environ.get("YM_PASS")

# ניהול תקציב זמן וכפילויות
TOTAL_BUDGET = 27.0
LAST_CALLS = {}
CACHE = {}
data_lock = Lock()
session = requests.Session()

def normalize_text(text):
    """ ניקוי טקסט להקראה טלפונית חלקה """
    if not text: return ""
    cleaned = re.sub(r'[^א-תa-zA-Z0-9\s.,?!:\-()"]', '', text)
    return re.sub(r'\s+', ' ', cleaned)[:350].strip()

@app.route("/chat", methods=["GET", "POST"])
def chat():
    start_time = time.time()
    ip = request.remote_addr
    audio_path = request.values.get("audio_file", "")
    
    # 1. ניהול כפילויות (הגנה מפני Retries של ה-Gateway)
    with data_lock:
        now = time.time()
        call_key = f"{ip}:{audio_path}"
        if audio_path and call_key in LAST_CALLS:
            if now - LAST_CALLS[call_key] < 2.0:
                return "OK"
        LAST_CALLS[call_key] = now
        if len(LAST_CALLS) > 2000: LAST_CALLS.clear()

    try:
        if request.values.get("hangup") == "yes": return "OK"
        if not audio_path:
            return "read=t-נא לומר את השאלה לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        clean_path = audio_path.lstrip("/")
        
        # בדיקת Cache
        if clean_path in CACHE:
            return CACHE[clean_path]

        # 2. הורדת קובץ (בדיקת גודל בסיסית בלבד)
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={quote(YM_USER)}&password={quote(YM_PASS)}&path={quote(clean_path)}"
        
        try:
            res = session.get(audio_url, timeout=12)
            res.raise_for_status()
            
            # הגנה רק מפני קבצים ריקים לחלוטין (מתחת ל-200 בייטים)
            if len(res.content) < 200:
                logger.warning(f"File too small: {len(res.content)} bytes")
                return "id_list_message=t-לא הוקלט שמע, נסה שוב&goto=."
                
            audio_content = res.content
        except Exception as e:
            logger.error(f"Download error: {e}")
            return "id_list_message=t-תקלה זמנית בתקשורת&goto=."

        # 3. עיבוד AI - השארת זיהוי הדיבור למודל
        base64_audio = base64.b64encode(audio_content).decode("utf-8")
        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{"parts": [
                {"text": "הקשב לשמע. אם יש דיבור, ענה עליו בקצרה מאוד בעברית. אם מדובר בשקט או רעש בלבד, ענה רק: לא שמעתי."},
                {"inline_data": {"mime_type": "audio/wav", "data": base64_audio}}
            ]}]
        }

        ai_text = None
        try:
            # שליחה ל-Gemini עם Timeout קשיח
            res_ai = session.post(gemini_url, json=payload, timeout=12)
            res_ai.raise_for_status()
            data = res_ai.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            if parts:
                ai_text = parts[0].get("text", "").strip()
        except Exception as e:
            logger.error(f"AI error: {e}")

        # 4. ניתוח תשובה והחזרה
        if not ai_text or "לא שמעתי" in ai_text or len(ai_text) < 2:
            return "id_list_message=t-לא שמעתי את דבריך בבירור, נסה שנית&goto=."

        final_response = normalize_text(ai_text)
        response_string = f"id_list_message=t-{final_response}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"
        
        with data_lock:
            CACHE[clean_path] = response_string
            if len(CACHE) > 500: CACHE.clear()
            
        logger.info(f"Success | Res: {final_response[:40]}...")
        return response_string

    except Exception as e:
        logger.error(f"Global Crash: {e}")
        return "id_list_message=t-אירעה שגיאה, נסו שוב&goto=."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
