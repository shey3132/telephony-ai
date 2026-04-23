from flask import Flask, request

app = Flask(__name__)

@app.route('/upload', methods=['POST'])
def upload_audio():
    # כאן השרת מקבל את קובץ השמע מהטלפון
    if 'file' in request.files:
        audio = request.files['file']
        # בינתיים רק נדפיס שקיבלנו קובץ
        print(f"Received audio file: {audio.filename}")
        return "OK", 200
    return "No file received", 400

@app.route('/')
def home():
    return "The AI Server is Running!"

if __name__ == '__main__':
    app.run()
