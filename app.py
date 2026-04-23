from flask import Flask, request
import google.generativeai as genai
import os
import requests

app = Flask(__name__)

# הגדרת ה-AI
genai.configure(api_key=os.environ.get("GEMINI_KEY"))
model = genai.GenerativeModel('gemini-pro')

@app.route('/upload', methods=['POST', 'GET'])
def upload():
    # המערכת הטלפונית שולחת קישור לקובץ ההקלטה בפרמטר 'url'
    audio_url = request.values.get('url')
    
    if not audio_url:
        return "read=t-לא התקבלה הקלטה.="

    try:
        # כאן אנחנו צריכים להפוך קול לטקסט. 
        # בגלל שזה שרת חינמי, הדרך הכי פשוטה היא שהמערכת הטלפונית
        # תעשה את ה-STT. אם המערכת שלך ממש לא מסוגלת,
        # אנחנו נשתמש ב-API של Gemini שיודע לקבל גם קבצי שמע.
        
        # לצורך הבדיקה הראשונה של הקלטה, נניח שהמערכת שולחת טקסט ב-v
        # אם אתה רוצה שהשרת ינתח קובץ שמע ממש, נצטרך להוסיף ספרית עיבוד קול.
        
        user_text = request.values.get('v', 'הודעה קולית התקבלה') 
        
        response = model.generate_content(user_text)
        return f"read=t-{response.text}="
        
    except Exception as e:
        return f"read=t-שגיאה בעיבוד הקול: {str(e)}="

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    # התעלמות מהודעות ניתוק
    if request.values.get('hangup') == 'yes':
        return "OK"

    user_text = request.values.get('v', '')
    
    # שלב א: כניסה ראשונה - מבקשים מהמשתמש לדבר
    if not user_text:
        # משתמשים ב-read כדי לפתוח מיקרופון (stt) ולשמור את התוצאה בפרמטר v
        return "read=t-שלום, אני מקשיב, מה השאלה שלך?=v,stt,he-IL,no,yes"

    # שלב ב: יש לנו טקסט מהמשתמש, שולחים ל-AI
    try:
        response = model.generate_content(user_text)
        ai_text = response.text.replace('"', '').replace("'", "").replace("=", "")
        
        # מחזירים את תשובת ה-AI ושוב פותחים מיקרופון לשאלה הבאה
        return f"id_list_message=t-{ai_text}&read=t-האם יש עוד שאלה?=v,stt,he-IL,no,yes"
        
    except Exception as e:
        return "id_list_message=t-חלה שגיאה בחיבור למוח הדיגיטלי&read=t-נסה לומר שוב?=v,stt,he-IL,no,yes"

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    app.run()
