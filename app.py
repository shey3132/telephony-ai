import os
import base64
import requests
import logging
import re
import time
from urllib.parse import quote
from flask import Flask, request
from threading import Lock

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# קונפיגורציה
API_KEY = os.environ.get("GEMINI_KEY")
YM_USER = os.environ.get("YM_USER")
YM_PASS = os.environ.get("YM_PASS")

# הגדרות ניהול שיחה
RECORD_COMMAND = "read=t-{}={}"  # תבנית פקודה להקלטה מחדש
RECORD_PARAMS = "audio_file,yes,record,/,audio_file,no,yes,yes"

LAST_CALLS = {}
data_lock = Lock()
session = requests.Session()

def normalize_text(text):
    if not text: return ""
    cleaned = re.sub(r'[^א-תa-zA-Z0-9\s.,?!:\-()"]', '', text)
    return re.sub(r'\s+', ' ', cleaned)[:350].strip()

@app.route("/chat", methods=["GET", "POST"])
def chat():
    start_time = time.time()
    ip = request.remote_addr
    audio_path = request.values.get("audio_file", "")
    
    # 1. מניעת כפילויות
    with data_lock:
        now = time.time()
        call_key = f"{ip}:{audio_path}"
        if audio_path and call_key in LAST_CALLS:
            if now - LAST_CALLS[call_key] < 3.0:
                return "OK"
        LAST_CALLS[call_key] = now
        if len(LAST_CALLS) > 1000: LAST_CALLS.clear()

    try:
        if request.values.get("hangup") == "yes": return "OK"
        
        # הודעת פתיחה ראשונית
        if not audio_path:
            return RECORD_COMMAND.format("נא לומר את שאלה לאחר הצליל", RECORD_PARAMS)

        clean_path = audio_path.lstrip("/")
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile" \
                    f"?isLogin=yes&username={quote(YM_USER)}&password={quote(YM_PASS)}&path={quote(clean_path)}"
        
        # 2. הורדה עם המתנה לסנכרון הקובץ
        audio_content = None
        for attempt in range(3):
            try:
                res = session.get(audio_url, timeout=10)
                res.raise_for_status()
                if len(res.content) < 800:
                    time.sleep(1.5)
                    continue
                audio_content = res.content
                break
            except:
                time.sleep(1)

        # שגיאה: קובץ לא תקין - מחזירים להקלטה מחדש במקום לצאת
        if not audio_content:
            logger.warning("File missing or too small after retries")
            return RECORD_COMMAND.format("סליחה, ההקלטה לא נקלטה. אפשר לנסות שוב?", RECORD_PARAMS)

        # 3. עיבוד AI
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

        # שגיאה: ה-AI לא הבין או שקט - מחזירים להקלטה מחדש
        if not ai_text or "לא שמעתי" in ai_text:
            return RECORD_COMMAND.format("לא הצלחתי לשמוע את דבריך, ננסה שוב?", RECORD_PARAMS)

        # 4. הצלחה - החזרת התשובה והצעה לשאלה נוספת (שוב עם read)
        final_response = normalize_text(ai_text)
        logger.info(f"Success! Response: {final_response[:30]}")
        
        return RECORD_COMMAND.format(f"{final_response}. האם יש לך עוד שאלה?", RECORD_PARAMS)

    except Exception as e:
        logger.error(f"Global Crash: {e}")
        return RECORD_COMMAND.format("אירעה שגיאה קלה, אפשר לנסות שוב?", RECORD_PARAMS)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
