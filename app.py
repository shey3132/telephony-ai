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
        
        # בניית כתובת ההורדה עם פרטי הגישה שלך
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?token={ym_user}:{ym_pass}&path={audio_path}"
        
        # הורדת הקובץ מהשרת של ימות המשיח
        audio_res = requests.get(audio_url)
        if audio_res.status_code != 200:
            return f"id_list_message=t-שגיאה בהורדת הקובץ. קוד שגיאה {audio_res.status_code}&go_to_folder=."

        audio_data = audio_res.content
        
        # הכנת הקובץ לשליחה לבינה המלאכותית
        audio_part = {
            "mime_type": "audio/wav",
            "data": audio_data
        }
        
        # שליחה ל-AI עם הנחיה ברורה
        prompt = "תמלל את ההקלטה וענה עליה בקצרה ובעברית. אם אין דיבור בהקלטה, תגיד שלא שמעת כלום."
        response = model.generate_content([prompt, audio_part])
        
        # ניקוי התשובה מתווים שעלולים לשבש את המערכת הטלפונית
        ai_text = response.text.replace('"', '').replace("=", "").replace("&", " ו- ").replace("\n", " ")
        
        # החזרת התשובה למאזין ופתיחת הקלטה נוספת
        return f"id_list_message=t-{ai_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        print(f"Error: {str(e)}")
        return f"id_list_message=t-חלה שגיאה בעיבוד הנתונים. {str(e)[:50]}&go_to_folder=."

@app.route('/')
def home():
    return "The AI Server is Running and Ready for Audio!"

if __name__ == '__main__':
    # הרצה מקומית לצורך בדיקה (ב-Render הוא משתמש ב-Gunicorn)
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
