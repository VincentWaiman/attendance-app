import json
import sys
import threading
import cv2
from flask import request
import torch
import numpy as np
from ultralytics import YOLO
from torchvision.ops import nms
from deep_sort_realtime.deepsort_tracker import DeepSort
from insightface.app import FaceAnalysis
import os
from concurrent.futures import ThreadPoolExecutor
import time
from datetime import datetime

from collections import defaultdict

from models import Student, db

import logging
from ultralytics.utils import LOGGER
LOGGER.setLevel(logging.CRITICAL)


from threading import Lock


latest_frames = defaultdict(lambda: None)
latest_frames_lock = Lock()


def recognize_and_capture(face_recognizer, face_image):
    """
    Runs face recognition and returns a tuple:
    ((name, confidence), face_image)
    """
    result = face_recognizer.identify_face(face_image)
    return result, face_image


class FaceRecognizer:
    def __init__(self, db_session, threshold=0.4, students=None):
        from insightface.app import FaceAnalysis  # Ensure this is imported
        self.face_app = FaceAnalysis(name='buffalo_l')
        self.face_app.prepare(ctx_id=0, det_size=(640, 640))
        self.threshold = threshold
        self.reference_faces = []
        self.reference_nims = []

        print(f"[FaceRecognizer] Students {students}")

        for student in students:
            nim = student['nim']
            db_student = db_session.query(Student).filter_by(nim=nim).first()
            if db_student and db_student.face_embedding:
                try:
                    # Convert BLOB (bytes) back to numpy array
                    emb = np.frombuffer(db_student.face_embedding, dtype=np.float32)

                    # Check again if the shape is correct
                    print(f"[DEBUG] Loaded embedding shape for {nim}: {emb.shape}")

                    if emb.shape == (512,):
                        self.reference_faces.append(emb)
                        self.reference_nims.append(nim)
                        print(f"[FaceRecognizer] Loaded embedding for {nim}")
                    else:
                        print(f"[FaceRecognizer] Invalid embedding shape for {nim}: {emb.shape}")
                except Exception as e:
                    print(f"[FaceRecognizer] Error loading embedding for {nim}: {str(e)}")
            else:
                print(f"[FaceRecognizer] No embedding found in DB for {nim}")

    def identify_face(self, face_image):
        """
        Returns a tuple (name, confidence). 
        If no face is found or the confidence is below threshold, returns (None, 0).
        """
        if face_image is None or face_image.size == 0:
            return (None, 0)
        faces = self.face_app.get(face_image)
        if not faces:
            return (None, 0)
        query_embedding = faces[0].embedding
        max_similarity = -1
        best_match = None
        for ref_embedding, nim in zip(self.reference_faces, self.reference_nims):
            similarity = np.dot(query_embedding, ref_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(ref_embedding)
            )
            if similarity > max_similarity:
                max_similarity = similarity
                best_match = nim
        return (best_match, max_similarity) if max_similarity > self.threshold else (None, 0)


def process_video_streams(video_sources, frame_skip=3, conf=0.7, nms_thresh=0.7, class_id=0,
                         face_threshold=0.4, track_iou_thresh=0.5,
                         face_recognition_interval=5, class_end_time=None, location=None, class_name=None, students=None, start_time=None, stop_event=None):
        
    print(f"--- Processing started at: {datetime.now().strftime('%A, %d %B %Y %H:%M:%S')} ---")
    print(f"Class will end at: {class_end_time}")
    print(f"Stop event is set? {stop_event.is_set() if stop_event else 'No event provided'}")
    print("[Stream] Trying to connect to", video_sources)
    window_name = f"Stream - {video_sources}"
    print(f"[show_stream] Starting stream for {video_sources}")
    if isinstance(video_sources, str) and video_sources.isdigit():
        video_sources = int(video_sources)
        
    cap = cv2.VideoCapture(video_sources, cv2.CAP_DSHOW)
    print(f"[DEBUG] cap.isOpened(): {cap.isOpened()}", flush=True)
    if not cap.isOpened():
        print(f"[ERROR] Failed to open video source: {video_sources} in thread {threading.current_thread().name}")
        return
    
    time.sleep(1)

    processing_start_datetime = datetime.now().strftime("%A, %d %B %Y %H:%M:%S")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    yolo_model = YOLO(r'D:\Calvin\Semester 8\TA\attandance-app\admin\utils\yolo11m_16_s.pt', verbose=False)
    tracker = DeepSort(max_age=30, n_init=3, max_iou_distance=0.7)
    face_recognizer = FaceRecognizer(db.session, threshold=face_threshold, students=students)
    nim_to_name = {student['nim']: student['name'] for student in students}
    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and fps > 0 else 30.0
    frame_interval = frame_skip / fps
    
    frame_count = 0

    track_info = {}
    person_presence = {}  # NEW
    
    track_info = {}
    track_last_recognition = {}
    recognition_futures = {}
    unknown_labels = {}
    executor = ThreadPoolExecutor(max_workers=4)
    last_annotations = []

    date_str = datetime.now().strftime("%Y-%m-%d")
    snip_base_path = os.path.join("static", "face_snips", class_name, date_str)
    os.makedirs(snip_base_path, exist_ok=True)
    
    # Check if start_time is provided
    if start_time:
        print(f"[INFO] Waiting until class start time: {start_time.strftime('%H:%M:%S')}")
        
        while datetime.now() < start_time:
            if stop_event and stop_event.is_set():
                print("[INFO] Stop event detected during wait.")
                cap.release()
                return  # Exit the function if stop event is triggered
            time.sleep(0.01)  # Sleep for 1 second before checking again

        print(f"[INFO] Class start time reached: {datetime.now().strftime('%H:%M:%S')}")
        
    fail_count = 0
    max_fail = 10
    
    while True:
        try:
            if stop_event and stop_event.is_set():
                print("[INFO] Stop event detected.")
                break

            if class_end_time and datetime.now() >= class_end_time:
                print("[INFO] Class has ended.")
                break
            
            for _ in range(5):  
                cap.grab()

            ret, frame = cap.read()
            if not ret:
                fail_count += 1
                print(f"[WARNING] Failed to read frame ({fail_count}/{max_fail})")
                if fail_count >= max_fail:
                    print("[ERROR] Maximum failed reads reached, exiting loop.")
                    break
                time.sleep(0.5)
                continue
            fail_count = 0 

            frame_count += 1
            current_time = time.time()
            currently_present_ids = set()

            if frame_count % frame_skip == 0:
                results = yolo_model(frame, device=device)
                detections = []
                for result in results:
                    boxes = torch.tensor(result.boxes.xyxy.cpu().numpy())
                    confidences = torch.tensor(result.boxes.conf.cpu().numpy())
                    class_ids = torch.tensor(result.boxes.cls.cpu().numpy().astype(int))
                    nms_indices = nms(boxes, confidences, nms_thresh)
                    for i in nms_indices:
                        if class_ids[i].item() != class_id or confidences[i].item() < conf:
                            continue
                        x1, y1, x2, y2 = map(int, boxes[i].numpy())
                        detections.append([[x1, y1, x2 - x1, y2 - y1], confidences[i].item(), class_id])

                tracks = tracker.update_tracks(detections, frame=frame)
                annotations = []

                for track in tracks:
                    if track.is_confirmed():
                    
                        currently_present_ids.add(track.track_id) 
                        x1, y1, x2, y2 = map(int, track.to_ltrb())
                        x1, y1 = max(0, x1), max(0, y1)
                        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
                        if x2 <= x1 or y2 <= y1:
                            continue

                        face_roi = frame[y1:y2, x1:x2].copy()

                        if track.track_id not in track_info:
                            now = datetime.now()
                            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                            track_info[track.track_id] = {
                                'label': 'Unknown',
                                'conf': 0,
                                'snapshot_saved': False,
                                'appearance_start': now,
                                'present': True,
                                'first_seen': timestamp,
                                'last_seen': timestamp
                            }
                        elif not track_info[track.track_id].get('present', False):
                                track_info[track.track_id]['appearance_start'] = datetime.now()
                                track_info[track.track_id]['present'] = True
                                
                        track_info[track.track_id]['last_seen'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        
                        last_time = track_last_recognition.get(track.track_id, 0)
                        
                        if current_time - track_last_recognition.get(track.track_id, 0) >= face_recognition_interval:
                            track_last_recognition[track.track_id] = current_time
                            future = executor.submit(recognize_and_capture, face_recognizer, face_roi)
                            recognition_futures[track.track_id] = future

                        if track.track_id in recognition_futures and recognition_futures[track.track_id].done():
                            (new_nim, new_conf), captured_roi = recognition_futures[track.track_id].result()
                            if new_nim is None:
                                if track.track_id not in unknown_labels:
                                    unknown_labels[track.track_id] = f"Unknown{len(unknown_labels)}"
                                new_label = unknown_labels[track.track_id]
                            else:
                                student_name = nim_to_name.get(new_nim, "UnknownName").replace(" ", "_")  # Nama student
                                new_label = f"{new_nim}_{student_name}"
                                if track.track_id in unknown_labels:
                                    unknown_path = os.path.join(snip_base_path, f"{unknown_labels[track.track_id]}.jpg")
                                    if os.path.exists(unknown_path):
                                        os.remove(unknown_path)
                                    del unknown_labels[track.track_id]

                            if new_conf > track_info[track.track_id]['conf'] or not track_info[track.track_id]['snapshot_saved']:
                                # Update label and confidence regardless
                                track_info[track.track_id]['label'] = new_label
                                track_info[track.track_id]['conf'] = new_conf

                                # Save the face snapshot, even if unknown
                                snip_path = os.path.join(snip_base_path, f"{new_label}.jpg")
                                cv2.imwrite(snip_path, captured_roi)

                                track_info[track.track_id]['snapshot_saved'] = True

                        annotations.append((x1, y1, x2, y2, track_info[track.track_id]['label']))

                last_annotations = annotations

            for (x1, y1, x2, y2, name) in last_annotations:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, name, (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            ret2, jpeg = cv2.imencode('.jpg', frame)
            print("ret2:", ret2, "video_sources:", video_sources)
            if ret2 and str(video_sources):
                with latest_frames_lock:
                    latest_frames[video_sources] = jpeg.tobytes()
                print(f"[DEBUG] Saved frame for {video_sources}", flush=True) 
                
            if stop_event and stop_event.is_set():
                print("[INFO] Stop event triggered.")
                break

            if class_end_time and datetime.now() >= class_end_time:
                print("[INFO] Class end time reached.")
                break
        except Exception as e:
            print(f"[CRASH] Thread crashed: {repr(e)}", file=sys.stderr, flush=True)
            break
            
    cap.release()
    
    cv2.destroyAllWindows()

    # Finalize any ongoing presence
    now = datetime.now()
    for track_id, info in track_info.items():
        if info.get('present', False):
            start_time = info.get('appearance_start')
            if start_time:
                duration = (now - start_time).total_seconds()
                label = info['label']
                if label not in person_presence:
                    person_presence[label] = []
                person_presence[label].append(duration)
            info['present'] = False
            

    overall_person_info = {}
    for label, durations in person_presence.items():
        nim = label.split('_')[0] if "Unknown" not in label else label
        total_time = sum(durations)
        overall_person_info[nim] = {
            'label': label,
            'time': round(total_time, 1)
        }
            
    filtered_person_info = {}
    for name, info in overall_person_info.items():
        if info['time'] >= 20:
            filtered_person_info[name] = info
        else:
            # Remove the image if it exists
            snip_path = os.path.join(snip_base_path, f"{name}.jpg")
            if os.path.exists(snip_path):
                os.remove(snip_path)
                print(f"[CLEANUP] Removed snip for {name} (tracked {info['time']:.1f}s)")

    print(f"\n--- Processing started at: {processing_start_datetime} ---\n")
    print("Accumulated Person Timers:")
    for name, info in filtered_person_info.items():
        print(f"{name}:")
        print(f"  Time Seen: {info['time']:.1f} seconds")
        
    json_txt_path = os.path.join(snip_base_path, "attendance_summary.txt")
    with open(json_txt_path, 'w') as f:
        json.dump(filtered_person_info, f, indent=4)

    return {
        'processing_start': processing_start_datetime,
        'person_data': filtered_person_info,
        'class_name': class_name,
        'date_str': date_str
    }



def display_results(result, snip_folder="face_snips"):
    class_name = result.get("class_name", "UnknownClass")
    date_str = result.get("date_str", datetime.now().strftime("%Y-%m-%d"))
    print(result)

    for nim, info in result['person_data'].items():
        snip_path = os.path.join(snip_folder, class_name, date_str, f"{nim}.jpg")
        if os.path.exists(snip_path):
            img = cv2.imread(snip_path)
        else:
            img = np.zeros((200, 200, 3), dtype=np.uint8)
            cv2.putText(img, "No Snip", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        window_title = (
            f"{nim}: {info['time']:.1f} sec "
            f"(First: {info['first_seen']}, Last: {info['last_seen']})"
        )
        # cv2.imshow(window_title, img)

    # cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    
def generate_stream(camera_ip):
    print(f"[generate_stream] Streaming from {camera_ip}")
    while True:
        with latest_frames_lock:
            # print(f"LATEST FRAME {latest_frames}")
            frame = latest_frames.get(camera_ip)

            if frame is not None:
                yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                print(f"[generate_stream] No frame yet for {camera_ip}")
            time.sleep(0.05)

