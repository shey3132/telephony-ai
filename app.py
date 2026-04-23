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

# ניהול עומסים ותקציב זמן
TOTAL_BUDGET = 27.0
LAST_CALLS = {}
CACHE = {}
data_lock = Lock()
session = requests.Session()

def normalize_text(text):
    if not text: return ""
    # ניקוי תווים מיוחדים ששוברים את ה-API של ימות המשיח
    cleaned = re.sub(r'[^א-תa-zA-Z0-9\s.,?!:\-()"]', '', text)
    return re.sub(r'\s+', ' ', cleaned)[:350].strip()

@app.route("/chat", methods=["GET", "POST"])
def chat():
    start_time = time.time()
    ip = request.remote_addr
    audio_path = request.values.get("audio_file", "")
    
    # --- ניהול כפילויות (אותו קובץ שנשלח שוב) ---
    with data_lock:
        now = time.time()
        call_key = f"{ip}:{audio_path}"
        if audio_path and call_key in LAST_CALLS:
            if now - LAST_CALLS[call_key] < 2.0:
                logger.info("Duplicate request ignored")
                return "OK"
        LAST_CALLS[call_key] = now
        if len(LAST_CALLS) > 2000: LAST_CALLS.clear()

    try:
        if request.values.get("hangup") == "yes": return "OK"
        if not audio_path:
            return "read=t-נא לומר את השאלה לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        clean_path = audio_path.lstrip("/")
        
        # בדיקת Cache מהירה
        if clean_path in CACHE:
            return CACHE[clean_path]

        # --- הורדת קובץ ---
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={quote(YM_USER)}&password={quote(YM_PASS)}&path={quote(clean_path)}"
        
        audio_content = None
        try:
            res = session.get(audio_url, timeout=12)
            res.raise_for_status()
            
            # בדיקת גודל מינימלי בלבד (הגנה מפני קובץ ריק טכנית)
            if len(res.content) < 200:
                return "id_list_message=t-לא הוקלט שמע, נסה שוב&goto=."
            
            audio_content = res.content
        except Exception as e:
            logger.error(f"Download error: {e}")
            return "id_list_message=t-שגיאה בהורדת ההקלטה&goto=."

        # --- AI Processing (כאן קורה הקסם והזיהוי האמיתי) ---
        base64_audio = base64.b64encode(audio_content).decode("utf-8")
        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{"parts": [
                {"text": "הקשב לשמע. אם יש דיבור, ענה עליו בקצרה בעברית. אם מדובר בשקט, רעשי רקע בלבד או נשימות, ענה רק במילים: לא שמעתי."},
                {"inline_data": {"mime_type": "audio/wav", "data": base64_audio}}
            ]}]
        }

        ai_text = None
        # ניסיון אחד ממוקד (כדי לעמוד בלו"ז של הטלפוניה)
        try:
            res_ai = session.post(gemini_url, json=payload, timeout=12)
            res_ai.raise_for_status()
            data = res_ai.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            if parts:
                ai_text = parts[0].get("text", "").strip()
        except Exception as e:
            logger.error(f"AI error: {e}")

        # --- ניהול תגובה לפי החלטת ה-AI ---
        if not ai_text or "לא שמעתי" in ai_text or len(ai_text) < 2:
            logger.info("AI decided: No clear speech detected")
            return "id_list_message=t-לא שמעתי את דבריך בבירור, נסה שנית&goto=."

        final_response = normalize_text(ai_text)
        response_string = f"id_list_message=t-{final_response}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"
        
        # שמירה ב-Cache
        with data_lock:
            CACHE[clean_path] = response_string
            if len(CACHE) > 500: CACHE.clear()
            
        logger.info(f"Success! Response: {final_response[:40]}...")
        return response_string

    except Exception as e:
        logger.error(f"Global Crash: {e}")
        return "id_list_message=t-אירעה שגיאה, נסו שוב מאוחר יותר&goto=."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
