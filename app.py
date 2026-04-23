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
    # בודקים אם המאזין כבר אמר משהו
    user_text = request.values.get('v', '')
    
    # אם המשתמש עדיין לא אמר כלום (כניסה ראשונה לשלוחה)
    if not user_text:
        # פקודה למערכת הטלפונית: להשמיע הודעה ולפתוח מיקרופון לזיהוי דיבור
        return "read=t-שלום, אני מקשיב, מה השאלה שלך?=&api_add_listening=yes"

    # אם כבר יש טקסט מהמאזין, נשלח אותו ל-AI
    try:
        response = model.generate_content(user_text)
        ai_text = response.text
        # מחזירים את התשובה ופותחים שוב את המיקרופון לשאלה הבאה
        return f"read=t-{ai_text}=&api_add_listening=yes"
    except Exception as e:
        return "read=t-חלה שגיאה בעיבוד הנתונים, נסו שוב.=&api_add_listening=yes"

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    app.run()
