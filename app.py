from flask import Flask, request
import google.generativeai as genai
import os
import requests

app = Flask(__name__)

# הגדרת ה-AI
api_key = os.environ.get("GEMINI_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    model = None

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.values.get('hangup') == 'yes':
        return "OK"

    audio_path = request.values.get('audio_file')
    
    # כניסה ראשונה
    if not audio_path or audio_path == "":
        return "read=t-נא לומר את השאלה לאחר הצליל ולסיום להקיש סולמית=audio_file,yes,record,/,audio_file,no,yes,yes"

    try:
        ym_user = os.environ.get("YM_USER")
        ym_pass = os.environ.get("YM_PASS")
        
        # ניקוי הנתיב
        clean_path = audio_path.lstrip('/')
        
        # ניסיון הורדה ראשון
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={ym_user}&password={ym_pass}&path={clean_path}"
        audio_res = requests.get(audio_url)
        
        # ניסיון הורדה שני (גיבוי)
        if audio_res.status_code != 200:
             audio_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={ym_user}:{ym_pass}&path={clean_path}"
             audio_res = requests.get(audio_url)

        if audio_res.status_code != 200:
            return f"id_list_message=t-שגיאה בהורדת הקובץ קוד {audio_res.status_code}&read=t-נסה שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

        # שליחה ל-AI
        audio_part = {
            "mime_type": "audio/wav",
            "data": audio_res.content
        }
        
        prompt = "תמלל את ההקלטה וענה עליה בקצרה ובעברית. אם ההקלטה ריקה, תגיד שלא שמעת."
        response = model.generate_content([prompt, audio_part])
        
        ai_text = response.text.replace('"', '').replace("=", "").replace("&", " ו- ").replace("\n", " ")
        
        return f"id_list_message=t-{ai_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        return f"id_list_message=t-תקלה זמנית בבינה המלאכותית&read=t-נסה לומר שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
