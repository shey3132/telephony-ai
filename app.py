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
    user_text = request.values.get('v', '')
    if not user_text: return "read=t-איך אפשר לעזור?="
    response = model.generate_content(user_text)
    return f"read=t-{response.text}="

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    app.run()
