import os
import requests
import base64
from flask import Flask, request

app = Flask(__name__)
API_KEY = os.environ.get("GEMINI_KEY")

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.values.get('hangup') == 'yes':
        return "OK"

    audio_paths = request.values.getlist('audio_file')
    
    if not audio_paths or audio_paths[0] == "":
        return "read=t-נא לומר את השאלה לאחר הצליל ולסיום להקיש סולמית=audio_file,yes,record,/,audio_file,no,yes,yes"

    try:
        clean_path = audio_paths[-1].lstrip('/')
        ym_user = os.environ.get("YM_USER")
        ym_pass = os.environ.get("YM_PASS")
        
        # הורדת הקובץ
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={ym_user}&password={ym_pass}&path={clean_path}"
        response_audio = requests.get(audio_url)
        
        if response_audio.status_code != 200:
            return f"id_list_message=t-שגיאה בהורדת הקובץ&go_to_folder=."

        base64_audio = base64.b64encode(response_audio.content).decode('utf-8')
        
        # ניסיון ראשון: הגרסה היציבה v1 עם מודל flash
        # (שיניתי מ-v1beta ל-v1)
        gemini_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": "ענה בקצרה בעברית על השמע המצורף"},
                    {"inline_data": {"mime_type": "audio/wav", "data": base64_audio}}
                ]
            }]
        }
        
        res = requests.post(gemini_url, json=payload)
        data = res.json()
        
        # אם יש שגיאה (כמו ה-404 המפורסם), ננסה כתובת חלופית (Pro)
        if 'error' in data:
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={API_KEY}"
            # ב-Pro נשלח רק טקסט כגיבוי למקרה שהשמע בעייתי
            payload_fallback = {"contents": [{"parts": [{"text": "תגיד שאתה זמין אבל יש בעיה בעיבוד השמע"}]}]}
            res = requests.post(gemini_url, json=payload_fallback)
            data = res.json()

        # חילוץ הטקסט
        final_text = data['candidates'][0]['content']['parts'][0]['text']
        final_text = final_text.replace('"', '').replace('=', '').replace('&', ' ו- ').replace('\n', ' ')
        
        return f"id_list_message=t-{final_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        return f"id_list_message=t-סליחה, חלה תקלה במוח הדיגיטלי&read=t-נסו שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
