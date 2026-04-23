import os
import base64
import requests
import logging
import re
import time
from urllib.parse import quote
from flask import Flask, request
from threading import Lock

# לוגים בסיסיים ויציבים
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# קונפיגורציה
API_KEY = os.environ.get("GEMINI_KEY")
YM_USER = os.environ.get("YM_USER")
YM_PASS = os.environ.get("YM_PASS")

# ניהול תקציב זמן וכפילויות
LAST_CALLS = {}
CACHE = {}
data_lock = Lock()
session = requests.Session()

def normalize_text(text):
    """ ניקוי טקסט בסיסי להקראה טלפונית """
    if not text: return ""
    cleaned = re.sub(r'[^א-תa-zA-Z0-9\s.,?!:\-()"]', '', text)
    return re.sub(r'\s+', ' ', cleaned)[:350].strip()

@app.route("/chat", methods=["GET", "POST"])
def chat():
    start_time = time.time()
    ip = request.remote_addr
    audio_path = request.values.get("audio_file", "")
    
    # 1. מניעת כפילויות (Duplicate Request Guard)
    with data_lock:
        now = time.time()
        call_key = f"{ip}:{audio_path}"
        if audio_path and call_key in LAST_CALLS:
            if now - LAST_CALLS[call_key] < 2.0:
                return "OK"
        LAST_CALLS[call_key] = now
        if len(LAST_CALLS) > 1000: LAST_CALLS.clear()

    try:
        if request.values.get("hangup") == "yes": return "OK"
        if not audio_path:
            return "read=t-נא לומר את השאלה לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        clean_path = audio_path.lstrip("/")
        
        # 2. הורדת הקובץ עם בדיקת סף מינימלית
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={quote(YM_USER)}&password={quote(YM_PASS)}&path={quote(clean_path)}"
        
        try:
            res = session.get(audio_url, timeout=10)
            res.raise_for_status()
            
            # אם הקובץ קטן מ-300 בתים, זה Header ריק - אין טעם להמשיך ל-AI
            if len(res.content) < 300:
                logger.warning(f"Empty/Failed record: {len(res.content)} bytes")
                return "id_list_message=t-לא התקבלה הקלטה, נסה שוב&goto=."
                
            audio_content = res.content
        except Exception as e:
            logger.error(f"Download error: {e}")
            return "id_list_message=t-שגיאה זמנית בתקשורת&goto=."

        # 3. עיבוד AI פשוט
        base64_audio = base64.b64encode(audio_content).decode("utf-8")
        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{"parts": [
                {"text": "ענה בקצרה בעברית על השאלה בשמע. אם אין דיבור ברור, ענה רק: לא שמעתי."},
                {"inline_data": {"mime_type": "audio/wav", "data": base64_audio}}
            ]}]
        }

        ai_text = ""
        try:
            res_ai = session.post(gemini_url, json=payload, timeout=15)
            res_ai.raise_for_status()
            data = res_ai.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            if parts:
                ai_text = parts[0].get("text", "").strip()
        except Exception as e:
            logger.error(f"AI error: {e}")

        # 4. תגובה סופית
        if not ai_text or "לא שמעתי" in ai_text:
            return "id_list_message=t-לא הצלחתי להבין, נסה שנית&goto=."

        final_response = normalize_text(ai_text)
        return f"id_list_message=t-{final_response}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        logger.error(f"System error: {e}")
        return "id_list_message=t-אירעה שגיאה, נסו שוב&goto=."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
