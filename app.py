import os
import requests
import base64
from flask import Flask, request

app = Flask(__name__)
API_KEY = os.environ.get("GEMINI_KEY")

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    # 1. התעלמות מניתוקים
    if request.values.get('hangup') == 'yes':
        return "OK"

    # טיפול בפרמטר כפול שימות המשיח לפעמים שולחת
    audio_paths = request.values.getlist('audio_file')
    
    # 2. אין קובץ? מבקשים מהמאזין לדבר
    if not audio_paths or audio_paths[0] == "":
        return "read=t-נא לומר את השאלה לאחר הצליל ולסיום להקיש סולמית=audio_file,yes,record,/,audio_file,no,yes,yes"

    try:
        # לוקחים את הנתיב האחרון ברשימה ומנקים אותו
        clean_path = audio_paths[-1].lstrip('/')
        
        ym_user = os.environ.get("YM_USER")
        ym_pass = os.environ.get("YM_PASS")
        
        # 3. מורידים את הקובץ מהמערכת שלך
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={ym_user}&password={ym_pass}&path={clean_path}"
        response_audio = requests.get(audio_url)
        
        if response_audio.status_code != 200:
            return f"id_list_message=t-תקלה בהורדת הקובץ מהמערכת&read=t-נסו שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

        # 4. הופכים את הקול לטקסט מקודד כדי לשלוח לגוגל ישירות
        base64_audio = base64.b64encode(response_audio.content).decode('utf-8')
        
        # הכתובת הישירה והמדויקת של גוגל (עוקף את כל ספריות הפייתון)
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": "Analyze this audio. Answer concisely in Hebrew. If it's silent or unclear, say you didn't hear anything."},
                    {"inline_data": {
                        "mime_type": "audio/wav",
                        "data": base64_audio
                    }}
                ]
            }]
        }
        
        headers = {'Content-Type': 'application/json'}
        
        # 5. שליחה לגוגל
        gemini_response = requests.post(gemini_url, json=payload, headers=headers)
        gemini_data = gemini_response.json()
        
        # 6. בדיקה אם גוגל החזירו שגיאה
        if 'error' in gemini_data:
            print(f"GEMINI ERROR: {gemini_data['error']}")
            return f"id_list_message=t-מפתח הבינה המלאכותית שגוי או חסום&read=t-נסו לומר שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"
            
        # 7. חילוץ התשובה מתוך ה-JSON של גוגל
        final_text = gemini_data['candidates'][0]['content']['parts'][0]['text']
        
        # ניקוי תווים בעייתיים למערכת ימות המשיח
        final_text = final_text.replace('"', '').replace('=', '').replace('&', ' ו- ').replace('\n', ' ')
        
        return f"id_list_message=t-{final_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return f"id_list_message=t-תקלה פנימית בשרת&read=t-נסו לומר שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

@app.route('/')
def home():
    return "The Direct REST API Server is LIVE!"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
