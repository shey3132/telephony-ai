from flask import Flask, request
import google.generativeai as genai
import os

app = Flask(__name__)

# הגדרת ה-AI (המפתח יגיע מהגדרות השרת)
genai.configure(api_key=os.environ.get("GEMINI_KEY"))
model = genai.GenerativeModel('gemini-pro')

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    # קבלת הטקסט מהמערכת הטלפונית
    user_text = request.values.get('v', '')
    
    if not user_text:
        return "read=t-שלום, במה אני יכול לעזור?="

    try:
        # שליחת השאלה ל-AI
        response = model.generate_content(user_text)
        ai_text = response.text
        
        # החזרת התשובה לטלפון (בפורמט הקראה)
        return f"read=t-{ai_text}="
    except Exception as e:
        return "read=t-מצטער, יש לי תקלה קטנה במוח.="

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    app.run()
