import os
import base64
import requests
import logging
import time
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

# מניעת כפילויות (בזיכרון זמני)
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
def get_mime_type(path):
    p = path.lower()
    if p.endswith(".mp3"):
        return "audio/mpeg"
    if p.endswith(".wav"):
        return "audio/wav"
    if p.endswith(".gsm"):
        return "audio/gsm"
    if p.endswith(".amr"):
        return "audio/amr"
    return "audio/wav"


def safe_extract_ai(data):
    """ חילוץ בטוח של תשובת Gemini """
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
        # Hangup
        # ----------------------
        if request.values.get("hangup") == "yes":
            return "OK"

        # ----------------------
        # Dedup calls
        # ----------------------
        call_id = request.values.get("ApiCallId")
        if call_id:
            if call_id in PROCESSED_CALLS:
                return "OK"
            PROCESSED_CALLS.add(call_id)

        # ----------------------
        # Input validation
        # ----------------------
        audio_path = request.values.get("audio_file")
        if not audio_path:
            return "read=t-אנא דבר לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        if not all([API_KEY, YM_USER, YM_PASS]):
            return "id_list_message=t-שגיאת קונפיגורציה&goto=."

        clean_path = audio_path.lstrip("/")
        mime_type = get_mime_type(clean_path)

        # ======================
        # 1. WAIT (קריטי!)
        # ======================
        time.sleep(0.8)

        audio_url = (
            "https://call2all.co.il/ym/api/DownloadFile"
            f"?isLogin=yes&username={quote(YM_USER)}"
            f"&password={quote(YM_PASS)}&path={quote(clean_path)}"
        )

        # ======================
        # 2. DOWNLOAD RETRY
        # ======================
        audio_content = None

        for attempt in range(3):
            try:
                res = session.get(audio_url, timeout=12)

                if res.status_code == 200:
                    size = len(res.content)

                    if size < 400:
                        logger.warning(f"Too small file: {size} bytes")
                        return "read=t-לא נשמע קול, נסה שוב=audio_file,yes,record,/,audio_file,no,yes,yes"

                    audio_content = res.content
                    break

            except Exception as e:
                logger.warning(f"Download attempt {attempt+1} failed: {e}")
                time.sleep(1)

        if not audio_content:
            return "id_list_message=t-שגיאת הורדת קובץ&goto=."

        # ======================
        # 3. GEMINI REQUEST
        # ======================
        base64_audio = base64.b64encode(audio_content).decode()

        gemini_url = (
            "https://generativelanguage.googleapis.com/v1/models/"
            f"gemini-1.5-flash:generateContent?key={API_KEY}"
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": "תמלל וענה בקצרה בעברית."},
                    {"inline_data": {
                        "mime_type": mime_type,
                        "data": base64_audio
                    }}
                ]
            }]
        }

        ai_text = None

        for attempt in range(2):
            try:
                res = session.post(gemini_url, json=payload, timeout=25)
                res.raise_for_status()

                data = res.json()
                ai_text = safe_extract_ai(data)

                if ai_text:
                    break

            except Exception as e:
                logger.warning(f"Gemini attempt {attempt+1} failed: {e}")
                time.sleep(1)

        # ======================
        # 4. RESPONSE HANDLING
        # ======================
        if not ai_text:
            return "id_list_message=t-המערכת עמוסה, נסה שוב&goto=."

        if "לא שמעתי" in ai_text:
            return "read=t-לא שמעתי, נסה שוב=audio_file,yes,record,/,audio_file,no,yes,yes"

        # ניקוי בסיסי
        ai_text = ai_text.replace("\n", " ").strip()[:300]

        # timeout safety
        if time.time() - start_time > 25:
            return "id_list_message=t-הבקשה ארוכה מדי, נסה שוב&goto=."

        logger.info(f"OK | {ai_text}")

        return (
            f"id_list_message=t-{ai_text}"
            "&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"
        )

    except Exception as e:
        logger.error(f"GLOBAL ERROR: {e}")
        return "id_list_message=t-שגיאה כללית&goto=."


# ======================
# HEALTH CHECK
# ======================
@app.route("/")
def home():
    return "OK - AI Telephony Server Running", 200


# ======================
# RUN
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
