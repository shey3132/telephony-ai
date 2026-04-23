import os
import base64
import requests
import logging
import re
import time
from urllib.parse import quote
from flask import Flask, request
from threading import Lock

# לוגים בתקן ייצור
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# קונפיגורציה
API_KEY = os.environ.get("GEMINI_KEY")
YM_USER = os.environ.get("YM_USER")
YM_PASS = os.environ.get("YM_PASS")

# הגדרות ניהול עומסים וכפילויות
TOTAL_BUDGET = 27.0
DUPLICATE_WINDOW = 2.0  # שניות לזיהוי כפילות של אותו קובץ
SPAM_WINDOW = 5.0       # חלון זמן לבדיקת הצפה
SPAM_LIMIT = 6          # מקסימום בקשות ל-IP בחלון הזמן
LAST_CALLS = {}
CACHE = {}
data_lock = Lock()
session = requests.Session()
session.headers.update({"User-Agent": "AI-Telephony-Gateway/1.3"})

def normalize_text(text):
    if not text: return ""
    cleaned = re.sub(r'[^א-תa-zA-Z0-9\s.,?!:\-()"]', '', text)
    return re.sub(r'\s+', ' ', cleaned)[:350].strip()

@app.route("/chat", methods=["GET", "POST"])
def chat():
    start_time = time.time()
    ip = request.remote_addr
    audio_path = request.values.get("audio_file", "")
    
    # 1. לוגיקת Rate Limit וכפילויות חכמה
    with data_lock:
        now = time.time()
        
        # יצירת מפתח ייחודי לשילוב של IP וקובץ
        call_key = f"{ip}:{audio_path}"
        
        # ניקוי זכרון אם ה-Dict גדל מדי
        if len(LAST_CALLS) > 5000: LAST_CALLS.clear()
        if len(CACHE) > 500: CACHE.clear()

        # בדיקת כפילות (אותו קובץ נשלח שוב בזמן קצר)
        if audio_path and call_key in LAST_CALLS:
            if now - LAST_CALLS[call_key] < DUPLICATE_WINDOW:
                logger.info(f"Duplicate request ignored: {audio_path}")
                return "OK" # התעלמות שקטה למניעת שבירת השיחה

        # ניהול היסטוריה ל-IP למניעת ספאם
        if ip not in LAST_CALLS: LAST_CALLS[ip] = []
        # השארת רק בקשות מה-5 שניות האחרונות (היסטוריית ה-IP נשמרת כרשימה)
        if isinstance(LAST_CALLS[ip], list):
            LAST_CALLS[ip] = [t for t in LAST_CALLS[ip] if now - t < SPAM_WINDOW]
            if len(LAST_CALLS[ip]) >= SPAM_LIMIT:
                logger.warning(f"Spam detected from IP: {ip}")
                return "id_list_message=t-נא להמתין מספר שניות&goto=.", 429
            LAST_CALLS[ip].append(now)
        else:
            LAST_CALLS[ip] = [now]

        # עדכון זמן הבקשה האחרונה למפתח הספציפי
        LAST_CALLS[call_key] = now

    try:
        if request.values.get("hangup") == "yes": return "OK"
        if not audio_path:
            return "read=t-נא לומר שאלה לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        clean_path = audio_path.lstrip("/")
        
        # בדיקת Cache
        if clean_path in CACHE:
            return CACHE[clean_path]

        if not all([API_KEY, YM_USER, YM_PASS]):
            return "id_list_message=t-שגיאת הגדרות מערכת&goto=."

        # 2. הורדת קובץ
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={quote(YM_USER)}&password={quote(YM_PASS)}&path={quote(clean_path)}"
        
        audio_content = None
        for attempt in range(2):
            if time.time() - start_time > TOTAL_BUDGET - 12: break
            try:
                res = session.get(audio_url, timeout=10)
                res.raise_for_status()
                # Silence Detection
                if len(res.content) < 600 or res.content.count(b'\x00') / len(res.content) > 0.9:
                    return "id_list_message=t-לא נשמע קול בהקלטה, נסה שוב&goto=."
                audio_content = res.content
                break
            except Exception:
                time.sleep(0.5)

        if not audio_content:
            return "id_list_message=t-תקלה בהורדת השמע&goto=."

        # 3. AI Processing
        base64_audio = base64.b64encode(audio_content).decode("utf-8")
        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{"parts": [
                {"text": "תמלל וענה בקצרה בעברית. אם אין דיבור ברור, ענה: לא שמעתי."},
                {"inline_data": {"mime_type": "audio/wav", "data": base64_audio}}
            ]}]
        }

        ai_text = None
        for attempt in range(2):
            elapsed = time.time() - start_time
            if elapsed > TOTAL_BUDGET - 6: break
            try:
                res_ai = session.post(gemini_url, json=payload, timeout=min(20, TOTAL_BUDGET - elapsed))
                if res_ai.status_code == 429:
                    time.sleep(1.5)
                    continue
                res_ai.raise_for_status()
                data = res_ai.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                if parts:
                    ai_text = parts[0].get("text", "").strip()
                    if ai_text: break
            except Exception:
                time.sleep(1)

        # 4. Response & Cache
        if not ai_text or "לא שמעתי" in ai_text:
            return "id_list_message=t-לא הצלחתי להבין, נסה שנית&goto=."

        final_response = normalize_text(ai_text)
        response_string = f"id_list_message=t-{final_response}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"
        
        with data_lock:
            CACHE[clean_path] = response_string
            
        return response_string

    except Exception as e:
        logger.error(f"Global Error: {e}")
        return "id_list_message=t-אירעה שגיאה, נסה שוב מאוחר יותר&goto=."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
