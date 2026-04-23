import os
import requests
from flask import Flask, request
import google.generativeai as genai

app = Flask(__name__)

# Configuration
API_KEY = os.environ.get("GEMINI_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
    # Force use of gemini-1.5-flash which is more stable for audio
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.values.get('hangup') == 'yes':
        return "OK"

    # Get the audio path from the request
    audio_path = request.values.get('audio_file')
    
    if not audio_path:
        return "read=t-נא לומר את השאלה לאחר הצליל ולסיום להקיש סולמית=audio_file,yes,record,/,audio_file,no,yes,yes"

    try:
        ym_user = os.environ.get("YM_USER")
        ym_pass = os.environ.get("YM_PASS")
        
        # Handle cases where audio_file might be a list
        if isinstance(audio_path, list):
            audio_path = audio_path[-1]
        
        clean_path = audio_path.lstrip('/')
        
        # Build download URL
        audio_url = f"https://call2all.co.il/ym/api/DownloadFile?isLogin=yes&username={ym_user}&password={ym_pass}&path={clean_path}"
        
        response_audio = requests.get(audio_url)
        if response_audio.status_code != 200:
            return f"id_list_message=t-שגיאה בהורדת הקובץ {response_audio.status_code}&read=t-נסו שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

        # Prepare for Gemini
        audio_data = {
            "mime_type": "audio/wav",
            "data": response_audio.content
        }
        
        prompt = "Analyze this audio. If it contains a question, answer it concisely in Hebrew. If it is silent or unclear, say you didn't hear anything."
        
        ai_response = model.generate_content([prompt, audio_data])
        
        # Clean the output text
        final_text = ai_response.text.replace('"', '').replace('=', '').replace('&', ' ו- ').replace('\n', ' ')
        
        return f"id_list_message=t-{final_text}&read=t-האם יש עוד שאלה?=audio_file,yes,record,/,audio_file,no,yes,yes"

    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        return f"id_list_message=t-חלה שגיאה בבינה המלאכותית&read=t-נסו לומר שוב?=audio_file,yes,record,/,audio_file,no,yes,yes"

@app.route('/')
def home():
    return "Server is live"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
