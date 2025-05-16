from datetime import datetime
import os
import shutil
import cv2
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user
import numpy as np
# from app import get_active_camera_ips
from models import AssignedClass, Attendance, Camera, Class, Schedule, Student, StudentClass, db
from flask import current_app
from insightface.app import FaceAnalysis

user_bp = Blueprint('user', __name__, template_folder='../templates')
# from app import db


@user_bp.route('/class')
@login_required
def class_user():
    assigned_classes = Class.query.join(AssignedClass).filter(AssignedClass.user_id == current_user.id).all()
    return render_template('user/class_user.html', classes=assigned_classes)

@user_bp.route('/classes')
@login_required
def classes():
    assigned_classes = Class.query.join(AssignedClass).filter(AssignedClass.user_id == current_user.id).all()
    return render_template('user/classes.html', classes=assigned_classes)

@user_bp.route('/is_class_active/<int:class_id>')
@login_required
def is_class_active(class_id):
    class_ = Class.query.get_or_404(class_id)
    now = datetime.now()
    current_day = now.strftime("%A")
    current_time = now.time()
    active = (
        class_.day == current_day and 
        class_.class_time_start <= current_time <= class_.class_time_end
    )
    return jsonify({'is_active': active})

def get_face_snips(class_):
    print(f"[GET FACE SNIPS] Getting from {class_.class_name}")
    
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    today_day = today.strftime('%A')
    
    is_class_active = (
        class_.day == today_day and
        class_.class_time_start <= today.time() <= class_.class_time_end
    )
    
    if not is_class_active:
        print("[GET FACE SNIPS] Class is not active, no snips returned.")
        return []

    class_name = class_.class_name
    snip_folder = os.path.join(current_app.root_path, 'static', 'face_snips', class_name, today_date)
    
    print(f"[GET FACE SNIPS] Snip folder: {snip_folder}")
    
    face_snips = []
    if os.path.isdir(snip_folder):
        for img_name in os.listdir(snip_folder):
            if not img_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue  # Skip file yang bukan gambar

            relative_path = os.path.join('face_snips', class_name, today_date, img_name).replace('\\', '/')
            
            filename_no_ext = os.path.splitext(img_name)[0]
            
            # Special case: Unknown
            if filename_no_ext.lower().startswith('unknown'):
                nim = "Unknown"
                nama = "Unknown"
            else:
                parts = filename_no_ext.split('_')
                if len(parts) >= 2:
                    nim = parts[0]
                    nama = '_'.join(parts[1:])  # Gabung lagi sisa bagian nama
                else:
                    nim = filename_no_ext
                    nama = ""

            face_snips.append({
                'path': relative_path,
                'nim': nim,
                'nama': nama
            })
    
    print(f"[GET FACE SNIPS] Found {len(face_snips)} snips")
    return face_snips



@user_bp.route('/load_snips/<int:class_id>')
@login_required
def load_snips(class_id):
    class_ = Class.query.get_or_404(class_id)
    
    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    class_name = class_.class_name

    snip_folder = os.path.join(current_app.root_path, 'static', 'face_snips', class_name, today_date)
    os.makedirs(snip_folder, exist_ok=True)
    snips_data = []  

    # print(f'[DEBUG] Looking for snips at: {snip_folder}')

    for filename in os.listdir(snip_folder):
        if filename.lower().endswith(('.jpg', '.png', '.jpeg')):
            filename_no_ext = os.path.splitext(filename)[0]

            if filename_no_ext.lower().startswith('unknown'):
                nim = "Unknown"
                nama = "Unknown"
            else:
                parts = filename_no_ext.split('_')
                if len(parts) >= 2:
                    nim = parts[0]
                    nama = '_'.join(parts[1:])
                else:
                    nim = filename_no_ext
                    nama = ""

            snips_data.append({
                'path': f'face_snips/{class_name}/{today_date}/{filename}',
                'nim': nim,
                'nama': nama
            })
    else:
        print('[DEBUG] Snip folder not found.')

    return jsonify({'snips': snips_data})

@user_bp.route('/class/<int:class_id>')
@login_required
def class_detail(class_id):
    class_ = Class.query.get_or_404(class_id)
    camera = Camera.query.filter_by(location=class_.location).first()
    camera_ip = camera.ip_address if camera else None

    now = datetime.now()
    current_day = now.strftime("%A")
    current_time = now.time()
    is_class_active = (
        class_.day == current_day and 
        class_.class_time_start <= current_time <= class_.class_time_end
    )

    # Ambil face snips waktu pertama buka halaman
    face_snips = get_face_snips(class_)

    return render_template(
        'user/class_detail.html', 
        class_=class_,
        camera_ip=camera_ip,
        class_code=class_.class_code,
        is_class_active=is_class_active,
        face_snips=face_snips
    )


@user_bp.route('/class_attendance/<int:class_id>')
@login_required
def class_attendance(class_id):
    class_ = Class.query.get_or_404(class_id)

    # Ambil semua mahasiswa yang tergabung di kelas ini
    students = db.session.query(Student).join(StudentClass).filter(StudentClass.class_id == class_id).all()

    # Ambil semua schedule untuk kelas ini, urutkan tanggal naik
    schedules = Schedule.query.filter_by(class_id=class_id).order_by(Schedule.tanggal).all()

    # Ambil semua attendance untuk kelas ini
    attendance_data = {}
    for student in students:
        attendance_data[student.nim] = {}
        for schedule in schedules:
            attendance = Attendance.query.filter_by(student_id=student.id, schedule_id=schedule.id).first()
            attendance_data[student.nim][schedule.id] = attendance.status if attendance else None
    return render_template('user/class_attendance.html', class_=class_, students=students, schedules=schedules, attendance_data=attendance_data)


# @user_bp.route('/validate_attendance/<int:schedule_id>')
# @login_required
# def validate_attendance(schedule_id):
#     schedule = Schedule.query.get_or_404(schedule_id)
#     # Logikamu buat validasi manual, atau tampilkan page buat cek & validasi
#     return render_template('user/validate_attendance.html', schedule=schedule)


@user_bp.route('/validate_attendance/<int:schedule_id>')
@login_required
def validate_attendance(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    class_ = schedule.class_

    today = datetime.now()
    today_date = today.strftime('%Y-%m-%d')
    class_name = class_.class_name

    snip_folder = os.path.join(current_app.root_path, 'static', 'face_snips', class_name, today_date)
    records = []

    if os.path.isdir(snip_folder):
        for filename in os.listdir(snip_folder):
            if filename.lower().endswith(('.jpg', '.png', '.jpeg')):
                filename_no_ext = os.path.splitext(filename)[0]

                # Parsing NIM
                if filename_no_ext.lower().startswith('unknown'):
                    nim = "Unknown"
                    nama = "Unknown"
                    student = None
                else:
                    parts = filename_no_ext.split('_')
                    nim = parts[0]
                    nama = '_'.join(parts[1:]) if len(parts) >= 2 else ""
                    student = Student.query.filter_by(nim=nim).first()

                # Ambil attendance
                attendance = None
                if student:
                    attendance = Attendance.query.filter_by(student_id=student.id, schedule_id=schedule.id).first()
                else:
                    # kalau Unknown, cari attendance dengan student_id NULL
                    attendance = Attendance.query.filter_by(student_id=None, schedule_id=schedule.id, label=filename_no_ext).first()

                # Gambar asli
                real_img_path = None
                student_folder = os.path.join(current_app.root_path, 'static', 'img_kampus')
                for angkatan_folder in os.listdir(student_folder):
                    candidate_path = os.path.join(student_folder, angkatan_folder, nim)
                    if os.path.isdir(candidate_path):
                        for real_img in os.listdir(candidate_path):
                            if real_img.lower().endswith(('.jpg', '.jpeg', '.png')):
                                real_img_path = os.path.join('img_kampus', angkatan_folder, nim, 'main.jpg').replace('\\', '/')
                            else:
                                for real_img in os.listdir(candidate_path):
                                    if real_img.lower().endswith(('.jpg', '.jpeg', '.png')):
                                        real_img_path = os.path.join('img_kampus', angkatan_folder, nim, real_img).replace('\\', '/')
                                        break
                        break

                records.append({
                    'nim': nim,
                    'nama': nama,
                    'snip_path': f'face_snips/{class_name}/{today_date}/{filename}',
                    'real_img_path': real_img_path,
                    'attendance_id': attendance.id if attendance else None,
                    'timestamp': attendance.timestamp if attendance else None,
                    'status': attendance.status if attendance else "Absent"
                })

    students = Student.query.join(StudentClass).filter(StudentClass.class_id == class_.id).all()
    return render_template('user/validate_attendance.html', schedule=schedule, records=records, students=students)


@user_bp.route('/delete_snip', methods=['POST'])
@login_required
def delete_snip():
    snip_path = request.form.get('snip_path')
    attendance_id = request.form.get('attendance_id')

    # print(f"[DEBUG] Delete snip: {snip_path}, attendance_id: {attendance_id}")
    # Hapus file snip
    if snip_path:
        full_path = os.path.join(current_app.static_folder, snip_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    # Hapus attendance dari DB kalau ada
    if attendance_id:
        attendance = Attendance.query.get(attendance_id)
        if attendance:
            db.session.delete(attendance)
            db.session.commit()

    flash('Snip dan attendance berhasil dihapus.', 'success')
    return redirect(request.referrer or url_for('user.dashboard'))



@user_bp.route('/validate_action', methods=['POST'])
@login_required
def validate_action():
    schedule_id = request.form.get('schedule_id')
    if not schedule_id:
        flash('Schedule ID tidak ditemukan.', 'danger')
        return redirect(request.referrer)

    attendance_ids = [aid for aid in request.form.getlist('attendance_id') if aid]
    validated_student_ids = []

    for attendance_id in attendance_ids:
        attendance = Attendance.query.get(attendance_id)
        if attendance:
            new_status = request.form.get(f'status-{attendance_id}')
            if new_status:
                attendance.status = new_status
                if attendance.student_id and new_status.lower() == 'present':
                    validated_student_ids.append(attendance.student_id)
                # print(f"[DEBUG] Update attendance {attendance_id} to {new_status}")

    schedule = Schedule.query.get(schedule_id)
    if schedule:
        schedule.is_validate = True

    db.session.commit()

    if schedule and validated_student_ids:
        try:
            class_ = schedule.class_
            tanggal_str = str(schedule.tanggal)
            class_name = class_.class_name if class_ else "unknown_class"
            print(f"[INFO FOR MOVING FILE] = {class_name}, {tanggal_str}")

            # Initialize face analysis once
            face_app = FaceAnalysis(name='buffalo_l')
            face_app.prepare(ctx_id=0, det_size=(640, 640))
            
            
            # Remove attendance_summary.txt
            summary_file = os.path.join('static', 'face_snips', class_name, tanggal_str, 'attendance_summary.txt')
            if os.path.exists(summary_file):
                try:
                    os.remove(summary_file)
                    print(f"[INFO] Removed summary file: {summary_file}")
                except Exception as summary_err:
                    print(f"[WARNING] Could not remove summary file: {summary_err}")

            for student_id in set(validated_student_ids):
                student = Student.query.get(student_id)
                if not student:
                    continue

                filename = f"{student.nim}_{student.name.replace(' ', '_')}.jpg"
                src_file = os.path.join('static', 'face_snips', class_name, tanggal_str, filename)
                dest_dir = os.path.join('static', 'img_kampus', str(student.batch_year), student.nim)
                dest_file = os.path.join(dest_dir, filename)

                if os.path.exists(src_file):
                    os.makedirs(dest_dir, exist_ok=True)
                    try:
                        base_name, ext = os.path.splitext(filename)
                        final_dest_file = dest_file
                        counter = 1

                        while os.path.exists(final_dest_file):
                            final_dest_file = os.path.join(dest_dir, f"{base_name}_{counter}{ext}")
                            counter += 1

                        shutil.move(src_file, final_dest_file)
                        print(f"[INFO] Moved {src_file} to {final_dest_file}")
                    except Exception as move_err:
                        print(f"[ERROR] Failed to move {src_file}: {move_err}")

                # Recompute embedding for this student
                try:
                    embeddings = []
                    for img_name in os.listdir(dest_dir):
                        img_path = os.path.join(dest_dir, img_name)
                        img = cv2.imread(img_path)
                        if img is not None:
                            faces = face_app.get(img)
                            if faces:
                                embeddings.append(faces[0].embedding)
                            else:
                                print(f"[WARNING] No face detected in image {img_name}")
                        else:
                            print(f"[WARNING] Failed to load image {img_name}")

                    if embeddings:
                        embeddings = np.array(embeddings)
                        avg_embedding = np.mean(embeddings, axis=0)
                        student.face_embedding = avg_embedding.tobytes()
                        db.session.commit()
                        print(f"[INFO] Updated face embedding for {student.nim}")
                    else:
                        print(f"[WARNING] No embeddings found for {student.nim}")
                except Exception as embed_err:
                    print(f"[ERROR] Failed to compute embedding for {student.nim}: {embed_err}")
        except Exception as e:
            print(f"[CRITICAL] Failed during image migration: {e}")

    flash('Validasi kehadiran berhasil diperbarui.', 'success')
    return redirect(url_for('user.classes', schedule_id=schedule_id))



# @user_bp.route('/assign_unknown', methods=['POST'])
# @login_required
# def assign_unknown():
#     snip_path = request.form.get('snip_path')
#     student_id = request.form.get('student_id')
#     attendance_id = request.form.get('attendance_id')

#     if not snip_path or not student_id or not attendance_id:
#         flash('Data tidak lengkap.', 'danger')
#         return redirect(request.referrer)

#     student = Student.query.get(student_id)
#     attendance = Attendance.query.get(attendance_id)

#     if not student or not attendance:
#         flash('Data tidak valid.', 'danger')
#         return redirect(request.referrer)

#     attendance.student_id = student.id
#     db.session.commit()

#     # Rename file
#     old_full_path = os.path.join(current_app.static_folder, snip_path)
#     new_filename = f"{student.nim}_{student.name.replace(' ', '_')}.jpg"
#     new_snip_path = os.path.join('face_snips', *snip_path.split('/')[1:3], new_filename)
#     new_full_path = os.path.join(current_app.static_folder, new_snip_path)

#     try:
#         os.rename(old_full_path, new_full_path)
#     except Exception as e:
#         flash(f'Gagal rename file: {e}', 'danger')
#         return redirect(request.referrer)

#     flash('Snip berhasil di-assign ke mahasiswa.', 'success')
#     return redirect(request.referrer)


@user_bp.route('/assign_unknown', methods=['POST'])
@login_required
def assign_unknown():
    snip_path = request.form.get('snip_path')
    student_id = request.form.get('student_id')
    attendance_id = request.form.get('attendance_id')

    if not snip_path or not student_id or not attendance_id:
        flash('Data tidak lengkap.', 'danger')
        return redirect(request.referrer)

    student = Student.query.get(student_id)
    attendance = Attendance.query.get(attendance_id)

    if not student or not attendance:
        flash('Data tidak valid.', 'danger')
        return redirect(request.referrer)

    # Rename file dulu
    old_full_path = os.path.join(current_app.static_folder, snip_path)
    today_folder = '/'.join(snip_path.split('/')[:3])  # misal: face_snips/classname/2025-04-28

    new_filename = f"{student.nim}_{student.name.replace(' ', '_')}.jpg"
    new_snip_path = os.path.join(today_folder, new_filename).replace("\\", "/")
    new_full_path = os.path.join(current_app.static_folder, new_snip_path)

    try:
        os.rename(old_full_path, new_full_path)
    except Exception as e:
        flash(f'Gagal rename file: {e}', 'danger')
        return redirect(request.referrer)

    # Setelah rename berhasil, baru update attendance
    attendance.student_id = student.id

    # ⚡ Tambahan: kalau kamu mau update snip_path juga di attendance (optional)
    # attendance.snip_path = new_snip_path

    db.session.commit()

    flash('Snip berhasil di-assign ke mahasiswa.', 'success')
    return redirect(request.referrer)
    
    
@user_bp.app_template_filter('durationformat')
def durationformat(value):
    if value is None:
        return "0 detik"
    value = int(value)
    hours = value // 3600
    minutes = (value % 3600) // 60
    seconds = value % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} jam")
    if minutes > 0:
        parts.append(f"{minutes} menit")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} detik")
    
    return ' '.join(parts)
