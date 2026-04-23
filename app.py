import os
import requests
from flask import Flask, request
import google.generativeai as genai

app = Flask(__name__)

API_KEY = os.environ.get("GEMINI_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
    # שימוש במודל הישן והיציב, שנתמך בכל גרסאות הספריה
    model = genai.GenerativeModel('gemini-pro-vision')
else:
    model = None

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.values.get('hangup') == 'yes':
        return "OK"

    audio_path = request.values.get('audio_file')
    
    if not audio_path:
        return "read=t-נא לומר את השאלה לאחר הצליל ולסיום להקיש סולמית=audio_file,yes,record,/,audio_file,no,yes,yes"

    try:
        ym_user = os.environ.get("YM_USER")
        ym_pass = os.environ.get("YM_PASS")
        
        if isinstance(audio_path, list):
            audio_path = audio_path[-1]
        clean_path = audio_path.lstrip('/')
        
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={ym_user}&password={ym_pass}&path={clean_path}"
        response_audio = requests.get(audio_url)
        
        if response_audio.status_code != 200:
            return f"id_list_message=t-שגיאה בהורדת הקובץ {response_audio.status_code}&read=t-נסו שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

        audio_data = {
            "mime_type": "audio/wav",
            "data": response_audio.content
        }
        
        prompt = "Analyze this audio. Answer concisely in Hebrew. If silent, say you didn't hear."
        
        # שימוש בפורמט הישן של פנייה למודל
        ai_response = model.generate_content([prompt, audio_data])
        
        final_text = ai_response.text.replace('"', '').replace('=', '').replace('&', ' ו- ').replace('\n', ' ')
        
        return f"id_list_message=t-{final_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        # אם יש שגיאה, המערכת תגיד לנו בדיוק מהי ולא סתם "חלה שגיאה"
        safe_error = str(e).replace('"', '').replace('=', '')[:100]
        return f"id_list_message=t-שגיאה בחיבור {safe_error}&read=t-נסו לומר שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

@app.route('/')
def home():
    return "Server is live"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
