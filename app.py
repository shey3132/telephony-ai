import os, base64, requests, logging, time, re, redis
from urllib.parse import quote
from flask import Flask, request

app = Flask(__name__)

# ======================
# CONFIG & INFRA
# ======================
API_KEY = os.environ.get("GEMINI_KEY")
YM_USER = os.environ.get("YM_USER")
YM_PASS = os.environ.get("YM_PASS")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

r = redis.from_url(REDIS_URL, decode_responses=True)
session = requests.Session()
session.headers.update({"User-Agent": "Enterprise-IVR/4.0"})

logging.basicConfig(level=logging.INFO, format="%(asctime)s | [%(call_id)s] | %(levelname)s | %(message)s")
logger = logging.getLogger("IVR_PRO")

# ======================
# LUA SCRIPTS (Atomic Operations)
# ======================
# סקריפט שבודק קאש ואם אין - נועל אטומית בפעולה אחת
LUA_LOCK_AND_CHECK = """
local cached = redis.call('get', KEYS[2])
if cached then return {1, cached} end
local lock = redis.call('set', KEYS[1], 'processing', 'NX', 'EX', ARGV[1])
if lock then return {0, 'ok'} else return {2, 'locked'} end
"""

# ======================
# ROBUST HELPERS
# ======================
def get_atomic_status(audio_path, ttl=45):
    """ משתמש ב-Lua כדי למנוע Race Condition בין ה-Lock ל-Cache """
    lock_key = f"lock:{audio_path}"
    cache_key = f"resp:{audio_path}"
    # returns: [status, value] -> 0: New lock, 1: Cached, 2: Busy
    return r.eval(LUA_LOCK_AND_CHECK, 2, lock_key, cache_key, ttl)

def get_stable_content(url):
    """ אימות קובץ מבוסס תוכן (Actual Byte Check) ללא הסתמכות על Headers """
    last_content_len = -1
    for i in range(4):
        try:
            res = session.get(url, timeout=7)
            if res.status_code == 200:
                curr_len = len(res.content)
                if curr_len > 600 and curr_len == last_content_len:
                    return res.content
                last_content_len = curr_len
            time.sleep(0.7 + (i * 0.3)) # Exponential jitter
        except Exception as e:
            logger.warning(f"Download check failed: {e}")
    return None

def clean_tts(text):
    if not text: return ""
    return re.sub(r'[*#_`-]', '', text).replace("\n", " ").strip()[:350]

# ======================
# MAIN ENGINE
# ======================
@app.route("/chat", methods=["GET", "POST"])
def chat():
    call_id = request.values.get("ApiCallId", "unknown")
    audio_path = request.values.get("audio_file")
    extra = {'call_id': call_id}

    try:
        # 1. HANGUP & INITIAL
        if request.values.get("hangup") == "yes":
            return "hangup=yes"
        
        if not audio_path:
            return "read=t-שלום, נא לומר את שאלתכם לאחר הצליל=audio_file,yes,record,/,audio_file,no,yes,yes"

        # 2. ATOMIC LOCK & IDEMPOTENCY (Lua Layer)
        # מפתח ייחודי שמשלב מסלול ו-ID כדי למנוע זליגת קאש בין שיחות
        unique_key = f"{call_id}:{audio_path.lstrip('/')}"
        status, value = get_atomic_status(unique_key)

        if status == 1: # Cached
            logger.info("Returning atomic cached response", extra=extra)
            return value
        if status == 2: # Busy
            return "OK" # ימות המשיח ינסו שוב או יחכו

        # 3. STABLE DOWNLOAD (Content-based)
        audio_url = (f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes"
                     f"&username={quote(YM_USER)}&password={quote(YM_PASS)}&path={quote(audio_path.lstrip('/'))}")
        
        audio_content = get_stable_content(audio_url)
        if not audio_content:
            r.delete(f"lock:{unique_key}")
            return "read=t-לא שמעתי אתכם טוב, נסו שנית=audio_file,yes,record,/,audio_file,no,yes,yes"

        # 4. AI CIRCUIT BREAKER LAYER
        b64 = base64.b64encode(audio_content).decode()
        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{"parts": [
                {"text": "system: ענה בעברית קצרה. אם אין דיבור ברור, ענה: [SILENCE]"},
                {"inline_data": {"mime_type": "audio/wav", "data": b64}}
            ]}]
        }

        ai_text = None
        try:
            ai_res = session.post(gemini_url, json=payload, timeout=18)
            ai_data = ai_res.json()
            
            # Explicit Error Handling
            if "error" in ai_data:
                logger.error(f"Gemini API Error: {ai_data['error']}", extra=extra)
            else:
                parts = ai_data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                if parts:
                    ai_text = parts[0].get("text", "").strip()
        except Exception as e:
            logger.error(f"AI Connection Failed: {e}", extra=extra)

        # 5. UX & FINAL RESPONSE
        if not ai_text or "[SILENCE]" in ai_text:
            response = "read=t-מצטער, לא שמעתי. אפשר לומר שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"
        else:
            final_txt = clean_tts(ai_text)
            response = f"id_list_message=t-{final_txt}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

        # 6. ATOMIC SAVE & LOCK RELEASE
        r.set(f"resp:{unique_key}", response, ex=600)
        logger.info("Process completed successfully", extra=extra)
        return response

    except Exception as e:
        logger.error(f"Global Crash: {e}", extra=extra)
        if 'unique_key' in locals(): r.delete(f"lock:{unique_key}")
        return "id_list_message=t-תקלה במערכת, נסו שוב מאוחר יותר&goto=."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
