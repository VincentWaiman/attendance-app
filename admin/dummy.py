from flask import Flask, Response, render_template_string
import cv2

app = Flask(__name__)

# Use your own video file path
video_path = r'D:\Calvin\Semester 8\TA\attandance-app\admin\720 Video\TPTK_1.mp4'
cap = cv2.VideoCapture(video_path)

def generate_frames():
    while True:
        success, frame = cap.read()
        if not success:
            print("⚠️  Video ended or not readable, looping...")
            cap.set(cv2.CAP_PROP_POS_FRAMES, 1)
            continue
        else:
            print("✅ Frame read successfully")

        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template_string('''
        <html>
        <head><title>Video Stream</title></head>
        <body>
            <h1>Dummy Video Stream</h1>
            <img src="{{ url_for('video') }}" width="640" height="480">
        </body>
        </html>
    ''')

@app.route('/video')
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Replace with your local IP (e.g., 192.168.1.10)
    app.run(host='0.0.0.0', port=7000, debug=False)
