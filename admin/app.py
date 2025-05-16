import logging
import os
import time
import cv2
from flask import Flask, Response, request, jsonify, render_template, redirect, flash, send_from_directory, stream_with_context, url_for
from flask_login import LoginManager, login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from models import Attendance, Camera, Class, Student, db, Users
# from new_with_date import process_video_streams
from routes.admin_routes import admin_bp
from routes.user_routes import user_bp
from flask_migrate import Migrate
from threading import Event, Thread, Timer
from flask_apscheduler import APScheduler
from datetime import datetime, timedelta
from utils.new_with_date_fix import display_results, generate_stream, process_video_streams
from apscheduler.schedulers.background import BackgroundScheduler
from waitress import serve


camera_queues = {}

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost:3306/attandance_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key' 
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db.init_app(app)
migrate = Migrate(app, db)

from collections import defaultdict
import threading


stop_event = Event()
scheduler = BackgroundScheduler()

from datetime import datetime
from models import Class, Schedule, Camera
# from app import db  # adjust this import based on your app structure

# active_classes = set()
active_classes = {}
active_classes_lock = threading.Lock()

from datetime import datetime, timedelta

from datetime import timedelta

def get_current_classes_with_cameras():
    now = datetime.now()
    current_day = now.strftime('%A')
    margin = timedelta(minutes=2)

    current_dt = datetime.combine(now.date(), now.time())

    upcoming_classes = db.session.query(Class).filter(
        Class.day == current_day,
        Class.class_time_start <= (current_dt + margin).time(),
        Class.class_time_end >= now.time()
    ).all()

    print(f"[Scheduler] Ongoing/upcoming classes: {[c.class_name for c in upcoming_classes]}")

    video_sources = []
    for class_ in upcoming_classes:
        camera = db.session.query(Camera).filter_by(location=class_.location).first()
        if camera:
            list_of_students = [
                {
                    'nim': sc.student_nim,
                    'name': sc.student.name
                }
                for sc in class_.student_classes
            ]
            video_sources.append({
                "class_id": class_.id,
                "class_name": class_.class_name,
                "ip_address": camera.ip_address,
                "start_time": datetime.combine(datetime.today(), class_.class_time_start),
                "end_time": datetime.combine(datetime.today(), class_.class_time_end),
                "location": class_.location,
                "students": list_of_students,
                "minimum_attendance_minutes": class_.minimum_attendance_minutes
            })
            
            print(video_sources)

    return video_sources

def run_face_recognition():
    
    with app.app_context():
        print(f"[Scheduler] Checking for new classes at {datetime.now().strftime('%H:%M:%S')}")

        current_classes = get_current_classes_with_cameras()

        for class_info in current_classes:
            class_id = class_info["class_id"]
            ip_address = class_info["ip_address"]
            start_time = class_info["start_time"]
            end_time = class_info["end_time"]
            class_name = class_info["class_name"]
            location = class_info["location"]
            students = class_info["students"]
            
            print(f"[IP ADDRESS] {ip_address}", flush=True)

            if datetime.now() >= end_time:
                continue

            with active_classes_lock:
                if class_id in active_classes:
                    if datetime.now() < active_classes[class_id]:  # Still running
                        # print(f"[Scheduler] Class '{class_name}' already running.")
                        continue
                    else:
                        # print(f"[Scheduler] Class '{class_name}' expired, restarting.")
                        del active_classes[class_id]

                active_classes[class_id] = end_time
                
            print(f"[IP ADDRESS] {ip_address}", flush=True)
            logging.debug(f"[IP ADDRESS] {ip_address}")
            logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')
            def runner(class_id=class_id, ip_address=ip_address, start_time=start_time, end_time=end_time, class_name=class_name, location=location, students=students):
                with app.app_context():
                    now = datetime.now()
                    open_camera_early_time = start_time - timedelta(minutes=1)
                    delay_until_open = (open_camera_early_time - now).total_seconds()
                    
                    ip_address = int(ip_address)
                    print(f"[IP ADDRESS] {ip_address}")
                    result = process_video_streams(
                        video_sources=ip_address,
                        stop_event=stop_event,
                        class_end_time=end_time,
                        location=location,
                        class_name=class_name,
                        students=students,
                        start_time=start_time
                    )

                    # display_results(result)
                    # print(f"[Scheduler] Class '{class_name}' finished.")

                    # 🔥 Simpan hasil ke database
                
                    date_str = result.get('date_str')
                    person_data = result.get('person_data', {})
                    class_name = result.get('class_name')

                    # 🔥 Insert Schedule baru
                    new_schedule = Schedule(
                        class_id=class_id,
                        tanggal=date_str,
                        is_validate=False
                    )
                    db.session.add(new_schedule)
                    db.session.commit()  

                    summary_lines = []
                    
                    # Convert minimum attendance to seconds for comparison
                    minimum_seconds = db.session.query(Class.minimum_attendance_minutes).filter_by(id=class_id).scalar() * 60
                    

                    for person_id, info in person_data.items():
                        label = info['label']
                        time_tracked = info['time']

                        if '_' in label:
                            nim, name = label.split('_', 1)
                        else:
                            nim, name = label, 'Unknown'

                        print(f"NIM: {nim}, Name: {name}, Time: {time_tracked:.1f}s")

                        # Check attendance status
                        attendance_status = 'Present' if info['time'] >= minimum_seconds else 'Absent'

                        # Save to database
                        if not person_id.startswith('Unknown'):
                            student = Student.query.filter_by(nim=nim).first()
                            if student:
                                attendance = Attendance(
                                    student_id=student.id,
                                    schedule_id=new_schedule.id,
                                    timestamp=info['time'],
                                    status=attendance_status
                                )
                                db.session.add(attendance)
                        else:
                            attendance = Attendance(
                                student_id=None,
                                schedule_id=new_schedule.id,
                                timestamp=info['time'],
                                status=attendance_status,
                                label=label
                            )
                            db.session.add(attendance)

                    db.session.commit()

                    # print(f"[Scheduler] Attendance and summary for class '{class_name}' on {date_str} saved successfully.")
                
                
            # stop_event.clear()
            # Calculate delay until 1 minute before class start
            delay = (start_time - timedelta(minutes=1) - datetime.now()).total_seconds()

            # Start thread at exactly 1 minute before class starts
            if delay > 0:
                Timer(delay, lambda: Thread(target=runner, daemon=True).start()).start()
            else:
                # If class is starting in less than a minute, start immediately
                Thread(target=runner, daemon=True).start()
            # Thread(target=runner, daemon=True).start()

def stop_face_recognition():
    # print(f"[Scheduler] Stopping face recognition at {datetime.now().strftime('%H:%M:%S')}")
    stop_event.set()


# ========== LOGIN MANAGEMENT ==========
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))


# ========== ROUTES ==========
# Register Blueprints
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(user_bp, url_prefix='/user')

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = Users.query.filter_by(email=email).first()
        if user and user.password == password:
            login_user(user)
            if user.is_admin:
                return redirect(url_for('admin.camera'))
            else:
                return redirect(url_for('user.class_user'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')


@app.route('/login', methods=['GET'])
def login_user_api():
    email = request.args.get('email')
    password = request.args.get('password')

    user = Users.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_admin": user.is_admin
    })


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/get_camera_urls')
@login_required
def get_camera_urls():
    cameras = Camera.query.all()
    camera_urls = [camera.ip_address for camera in cameras]
    return jsonify(camera_urls)


@app.route("/video_feed")
def video_feed():
    camera_ip = request.args.get("ip")
    class_code = request.args.get("class_code")

    if not camera_ip or not class_code:
        return "Missing 'ip' or 'class_code' parameter", 400

    camera = Camera.query.filter_by(ip_address=camera_ip).first()
    if not camera:
        return "Camera not found", 404

    now = datetime.now()
    current_day = now.strftime("%A")
    current_time = now.time()

    active_class = (
        Class.query
        .filter_by(location=camera.location, day=current_day)
        .filter(Class.class_time_start <= current_time, Class.class_time_end >= current_time)
        .first()
    )

    if not active_class:
        return "No active class", 403

    if active_class.class_code != class_code:
        return "Access denied: Not your class time", 403

    # Convert camera_ip ke int di sini
    try:
        camera_ip_int = int(camera_ip)
    except ValueError:
        return "Invalid camera IP format", 400

    return Response(generate_stream(camera_ip_int),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route('/snips/<camera>/<filename>')
def serve_snip(camera, filename):
    folder = os.path.join('face_snips', camera)
    return send_from_directory(folder, filename)

@app.template_filter('seconds_to_duration')
def seconds_to_duration(seconds):
    if seconds is None:
        return ''
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

# ========== DEV ONLY ==========
if __name__ == '__main__':
    import os

    # This avoids running the scheduler twice in debug mode
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        if not scheduler.running:
            print("[Scheduler] Adding face recognition job")
            scheduler.add_job(
                run_face_recognition,
                'interval',
                seconds=5,
                id='face_recognition_job',
                replace_existing=True,
                max_instances=1
            )
            scheduler.start()

    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)

# if __name__ == '__main__':
#     import os

#     if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
#         if not scheduler.running:
#             print("[Scheduler] Adding face recognition job")
#             scheduler.add_job(
#                 run_face_recognition,
#                 'interval',
#                 seconds=5,
#                 id='face_recognition_job',
#                 replace_existing=True,
#                 max_instances=1
#             )
#             scheduler.start()

#     print("✅ Starting server with Waitress on http://0.0.0.0:5000")
#     serve(app, host='0.0.0.0', port=5000, threads=16)
