from flask import Flask, request
import google.generativeai as genai
import os
import requests

app = Flask(__name__)

# הגדרת ה-AI
genai.configure(api_key=os.environ.get("GEMINI_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash') # גרסה שתומכת בקבצי שמע

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.values.get('hangup') == 'yes':
        return "OK"

    # קבלת הנתיב המלא של קובץ ההקלטה מהמערכת הטלפונית
    audio_path = request.values.get('audio_file')
    
    # אם אין קובץ שמע (כניסה ראשונה לשלוחה)
    if not audio_path:
        # פקודת הקלטה: השמעת הודעה והקלטה לפרמטר audio_file
        return "read=t-נא לומר את השאלה לאחר הצליל ולסיום להקיש סולמית=audio_file,yes,record,/,audio_file,no,yes,yes"

    try:
        # 1. הורדת קובץ השמע מהמערכת הטלפונית
        # (הכתובת המלאה נבנית מהנתיב שהתקבל)
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?path={audio_path}"
        audio_data = requests.get(audio_url).content
        
        # 2. שליחת הקובץ ל-Gemini לתמלול ומענה
        # אנחנו יוצרים "חלק" של קובץ שמע עבור ה-AI
        audio_part = {
            "mime_type": "audio/wav",
            "data": audio_data
        }
        
        prompt = "תמלל את ההקלטה וענה עליה בקצרה בעברית."
        response = model.generate_content([prompt, audio_part])
        ai_text = response.text.replace('"', '').replace("=", "")
        
        # 3. החזרת התשובה ופתיחת הקלטה חדשה
        return f"id_list_message=t-{ai_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        print(f"Error: {e}")
        return "id_list_message=t-חלה שגיאה בעיבוד השמע&go_to_folder=."

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    app.run()
