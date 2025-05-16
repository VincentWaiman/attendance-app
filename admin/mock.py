from apscheduler.schedulers.background import BackgroundScheduler
from threading import Event, Thread
from datetime import datetime, timedelta
import time

from utils.new_with_date_fix import display_results, process_video_streams

# === IP CAMERA STREAM URL(s) ===
# video_inputs = "rtsp://localhost:8554/video1"
video_inputs = "rtsp://localhost:8554/video1"
# video_inputs = r"D:\Calvin\Semester 8\TA\TAChrisvincent\RAW\videos\SDA_entry.mov"
# video_inputs = r"D:\Calvin\Semester 8\TA\attandance-app\admin\demo.mp4"

# === FIX: Use full datetime objects ===
start_time = datetime.now() + timedelta(seconds=10)
end_time = start_time + timedelta(minutes=1)

# === GLOBAL CONTROL OBJECTS ===
stop_event = Event()
scheduler = BackgroundScheduler()

def run_face_recognition():
    print(f"[Scheduler] Starting face recognition at {datetime.now().strftime('%H:%M:%S')}")
    stop_event.clear()

    def runner():
        result = process_video_streams(
            video_sources=video_inputs,
            stop_event=stop_event,
            class_end_time=end_time,
            location='1205',
            class_name='Topik dalam Teknologi Komputer',
            students=[{'nim': '212200160', 'name': 'Nathanael Sean Lim'}, {'nim': '212100113', 'name': 'Vincent Waiman'}, {'nim': '212101349', 'name': 'Samuel Christian'}, {"nim": '212100001', 'name': 'Prilly'}, {'nim': '212100002', 'name': 'Dilivio'}], 
        )
        display_results(result)

    Thread(target=runner, daemon=True).start()

def stop_face_recognition():
    print(f"[Scheduler] Stopping face recognition at {datetime.now().strftime('%H:%M:%S')}")
    stop_event.set()

# === SCHEDULE THE JOBS ===
scheduler.add_job(run_face_recognition, 'cron',
                  hour=start_time.hour, minute=start_time.minute, second=start_time.second)
scheduler.add_job(stop_face_recognition, 'cron',
                  hour=end_time.hour, minute=end_time.minute, second=end_time.second)

# === START SCHEDULER ===
print(f"[Scheduler] Scheduled start at {start_time.strftime('%H:%M:%S')} and stop at {end_time.strftime('%H:%M:%S')}")
scheduler.start()

try:
    while True:
        time.sleep(1)
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()
    print("[Scheduler] Gracefully shut down.")
