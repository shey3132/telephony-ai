import os
import base64
import requests
import logging
import time
import re
from urllib.parse import quote
from flask import Flask, request

app = Flask(__name__)

# ======================
# CONFIG
# ======================
API_KEY = os.environ.get("GEMINI_KEY")
YM_USER = os.environ.get("YM_USER")
YM_PASS = os.environ.get("YM_PASS")

session = requests.Session()
session.headers.update({"User-Agent": "AI-Telephony-Gateway/2.0"})

# מניעת כפילויות (בזיכרון זמני) - מומלץ לנקות מדי פעם בייצור
PROCESSED_CALLS = set()

# ======================
# LOGGING
# ======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ======================
# HELPERS
# ======================
def normalize_hebrew_text(text):
    """ ניקוי תווים מיוחדים שעלולים לשבש את המערכת הטלפונית """
    if not text: return ""
    # השארת אותיות, מספרים ופיסוק בסיסי בלבד
    cleaned = re.sub(r'[^א-תa-zA-Z0-9\s.,?!:\-()"]', '', text)
    return re.sub(r'\s+', ' ', cleaned).strip()

def get_mime_type(path):
    p = path.lower()
    if p.endswith(".mp3"): return "audio/mpeg"
    if p.endswith(".wav"): return "audio/wav"
    if p.endswith(".gsm"): return "audio/gsm"
    if p.endswith(".amr"): return "audio/amr"
    return "audio/wav"

def safe_extract_ai(data):
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None

# ======================
# MAIN ROUTE
# ======================
@app.route("/chat", methods=["GET", "POST"])
def chat():
    start_time = time.time()
    
    try:
        # ----------------------
        # 1. HANGUP HANDLING (תיקון קריטי!)
        # ----------------------
        # אם המשתמש ניתק או שהמערכת שולחת סיום - אנחנו חייבים לסגור נקי
        if request.values.get("hangup") == "yes":
            logger.info("Hangup received - closing session")
            return "hangup=yes" # פקודה לימות המשיח לסגור את השיחה סופית

        # ----------------------
        # 2. Dedup calls
        # ----------------------
        call_id = request.values.get("ApiCallId")
        if call_id:
            if call_id in PROCESSED_CALLS:
                return "OK"
            PROCESSED_CALLS.add(call_id)
            # ניקוי זכרון פשוט
            if len(PROCESSED_CALLS) > 1000: PROCESSED_CALLS.clear()

        # ----------------------
        # 3. Input validation
        # ----------------------
        audio_path = request.values.get("audio_file")
        if not audio_path:
            return "read=t-נא דבר לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        if not all([API_KEY, YM_USER, YM_PASS]):
            return "id_list_message=t-שגיאת קונפיגורציה&goto=."

        clean_path = audio_path.lstrip("/")
        mime_type = get_mime_type(clean_path)

        # WAIT לסנכרון הקובץ בשרת
        time.sleep(0.8)

        audio_url = (
            "https://call2all.co.il/ym/api/DownloadFile"
            f"?isLogin=yes&username={quote(YM_USER)}"
            f"&password={quote(YM_PASS)}&path={quote(clean_path)}"
        )

        # ----------------------
        # 4. DOWNLOAD WITH SIZE CHECK
        # ----------------------
        audio_content = None
        for attempt in range(3):
            try:
                res = session.get(audio_url, timeout=12)
                if res.status_code == 200:
                    size = len(res.content)
                    if size < 400:
                        logger.warning(f"File too small: {size} bytes")
                        return "read=t-לא שמעתי, נסה שוב=audio_file,yes,record,/,audio_file,no,yes,yes"
                    audio_content = res.content
                    break
                time.sleep(1)
            except Exception as e:
                logger.warning(f"Download attempt {attempt+1} failed: {e}")

        if not audio_content:
            return "id_list_message=t-שגיאה בקליטת השמע&goto=."

        # ----------------------
        # 5. GEMINI REQUEST
        # ----------------------
        base64_audio = base64.b64encode(audio_content).decode()
        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"

        payload = {
            "contents": [{
                "parts": [
                    {"text": "תמלל וענה בקצרה מאוד בעברית. אם אין דיבור, ענה רק 'לא שמעתי'."},
                    {"inline_data": {"mime_type": mime_type, "data": base64_audio}}
                ]
            }]
        }

        ai_text = None
        for attempt in range(2):
            try:
                res = session.post(gemini_url, json=payload, timeout=22)
                res.raise_for_status()
                ai_text = safe_extract_ai(res.json())
                if ai_text: break
            except Exception as e:
                logger.warning(f"Gemini attempt {attempt+1} failed: {e}")
                time.sleep(1)

        # ----------------------
        # 6. RESPONSE HANDLING
        # ----------------------
        if not ai_text or "לא שמעתי" in ai_text:
            return "read=t-מצטער, לא שמעתי טוב. נסה שוב=audio_file,yes,record,/,audio_file,no,yes,yes"

        # ניקוי ונירמול התשובה (קריטי להקראה נקייה)
        clean_response = normalize_hebrew_text(ai_text)[:350]

        # בדיקת Timeout לפני שליחה
        if time.time() - start_time > 26:
             return "id_list_message=t-התהליך לקח זמן רב מדי, נסה שנית&goto=."

        logger.info(f"AI SUCCESS | {clean_response[:50]}...")

        # החזרת תשובה והמשך הקלטה
        return (
            f"id_list_message=t-{clean_response}"
            "&read=t-האם יש לך עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"
        )

    except Exception as e:
        logger.error(f"GLOBAL ERROR: {e}")
        return "id_list_message=t-אירעה שגיאה כללית&goto=."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
