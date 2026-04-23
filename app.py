from flask import Flask, request
import google.generativeai as genai
import os
import requests

app = Flask(__name__)

# הגדרת ה-AI מתוך משתני הסביבה (Environment Variables)
api_key = os.environ.get("GEMINI_KEY")
if api_key:
    genai.configure(api_key=api_key)
    # שימוש במודל 1.5 פלאש שתומך בקבצי קול בצורה מעולה
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
else:
    model = None

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    # התעלמות מהודעות ניתוק של המערכת
    if request.values.get('hangup') == 'yes':
        return "OK"

    # קבלת נתיב קובץ השמע שהמערכת הקליטה
    audio_path = request.values.get('audio_file')
    
    # שלב א: אם אין עדיין קובץ (כניסה ראשונה לשלוחה)
    if not audio_path or audio_path == "":
        return "read=t-נא לומר את השאלה לאחר הצליל ולסיום להקיש סולמית=audio_file,yes,record,/,audio_file,no,yes,yes"

    # שלב ב: עיבוד קובץ השמע
try:
        ym_user = os.environ.get("YM_USER")
        ym_pass = os.environ.get("YM_PASS")
        
        # ניקוי הנתיב למקרה שיש סלאשים מיותרים
        clean_path = audio_path.lstrip('/')
        
        # בניית ה-URL לפי הפורמט המדויק של API ימות המשיח
        # שים לב: השתמשנו ב-password במקום token ליתר ביטחון
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={ym_user}&password={ym_pass}&path={clean_path}"
        
        print(f"Attempting to download from: {audio_url}") # זה יופיע בלוגים שלך
        
        audio_res = requests.get(audio_url)
        
        # אם זה עדיין נכשל, ננסה פורמט נוסף של כתובת
        if audio_res.status_code != 200:
             audio_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={ym_user}:{ym_pass}&path={clean_path}"
             audio_res = requests.get(audio_url)

        if audio_res.status_code != 200:
            return f"id_list_message=t-שגיאה בהורדת הקובץ. קוד {audio_res.status_code}&go_to_folder=."

        audio_data = audio_res.content
        
        # המשך הקוד (שליחה ל-AI)...
        audio_part = {
            "mime_type": "audio/wav",
            "data": audio_data
        }
        
        prompt = "תמלל את ההקלטה וענה עליה בקצרה ובעברית."
        response = model.generate_content([prompt, audio_part])
        ai_text = response.text.replace('"', '').replace("=", "").replace("&", " ו- ").replace("\n", " ")
        
        return f"id_list_message=t-{ai_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

@app.route('/')
def home():
    return "The AI Server is Running and Ready for Audio!"

if __name__ == '__main__':
    # הרצה מקומית לצורך בדיקה (ב-Render הוא משתמש ב-Gunicorn)
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
