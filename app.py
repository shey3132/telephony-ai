from flask import Flask, request
import google.generativeai as genai
import os
import requests

app = Flask(__name__)

# הגדרת ה-AI
api_key = os.environ.get("GEMINI_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
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
        
        # ניקוי נתיב (לפעמים מגיע כרשימה, לוקחים את האחרון)
        if isinstance(audio_path, list):
            audio_path = audio_path[-1]
        clean_path = audio_path.lstrip('/')
        
        # הורדת הקובץ
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={ym_user}&password={ym_pass}&path={clean_path}"
        audio_res = requests.get(audio_url)
        
        if audio_res.status_code != 200:
            return f"id_list_message=t-שגיאה בהורדת הקובץ&read=t-נסה שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

        # שליחה ל-AI בפורמט בטוח יותר
        audio_data = audio_res.content
        
        # יצירת התוכן לשליחה
        contents = [
            {
                "mime_type": "audio/wav",
                "data": audio_data
            },
            "תמלל את ההקלטה וענה עליה בקצרה בעברית. אם ההקלטה ריקה או שאין בה דיבור ברור, תענה שלא שמעת כלום."
        ]
        
        response = model.generate_content(contents)
        
        # ניקוי התשובה
        ai_text = response.text.replace('"', '').replace("=", "").replace("&", " ו- ").replace("\n", " ")
        
        return f"id_list_message=t-{ai_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        # הדפסת השגיאה המדויקת ללוגים של Render כדי שנדע מה קרה
        print(f"DEBUG ERROR: {str(e)}")
        return f"id_list_message=t-הבינה המלאכותית לא הצליחה לעבד את הקול.&read=t-נסה לומר שוב בקצרה?=audio_file,yes,record,/,audio_file,no,yes,yes"

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
