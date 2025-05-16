import csv
from datetime import datetime
import io
from flask import Blueprint, Response, render_template, request, redirect, flash, url_for, jsonify
from flask_login import login_required, current_user
from models import AssignedClass, Attendance, Student, StudentClass, db, Camera, Users, Major, Class
from werkzeug.utils import secure_filename
import os
import cv2
import numpy as np
from insightface.app import FaceAnalysis
import zipfile
import tempfile

import shutil
from werkzeug.utils import secure_filename
from flask import current_app

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')


@admin_bp.route('/camera')
@login_required
def camera():
    if not current_user.is_admin:
        return "Unauthorized", 403
    cameras = Camera.query.all()
    return render_template('camera_admin.html', cameras=cameras)


@admin_bp.route('/admin/delete_camera/<int:camera_id>', methods=['POST'])
@login_required
def delete_camera(camera_id):
    camera = Camera.query.get_or_404(camera_id)
    try:
        db.session.delete(camera)
        db.session.commit()
        flash('Camera deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to delete camera. Error: {str(e)}', 'danger')
    return redirect(url_for('admin.camera')) 


@admin_bp.route('/users')
@login_required
def users():
    if not current_user.is_admin:
        return "Unauthorized", 403
    users = Users.query.all()
    return render_template('users.html', users=users)

@admin_bp.route('/add-camera', methods=['POST'])
@login_required
def add_camera():
    name = request.form.get('name')
    ip_address = request.form.get('ip_address')
    location = request.form.get('location')

    new_camera = Camera(name=name, ip_address=ip_address, location=location)
    db.session.add(new_camera)
    db.session.commit()

    flash('New camera added successfully!', 'success')
    return redirect(url_for('admin.camera'))

@admin_bp.route('/add-user', methods=['POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        return "Unauthorized", 403

    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    is_admin = True if 'is_admin' in request.form else False

    new_user = Users(name=name, email=email, password=password, is_admin=is_admin)
    db.session.add(new_user)
    db.session.commit()

    return redirect(url_for('admin.users'))


@admin_bp.route('/update_user/<int:id>', methods=['POST'])
@login_required
def update_user(id):
    if not current_user.is_admin:
        return jsonify({'message': 'Unauthorized'}), 403

    user = Users.query.get_or_404(id)
    data = request.get_json()

    if 'name' in data:
        user.name = data['name']
    if 'email' in data:
        user.email = data['email']

    db.session.commit()
    return jsonify({'message': 'User updated successfully'})


@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return "Unauthorized", 403

    user = Users.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('admin.users'))


# ---- Majors ----
@admin_bp.route('/majors')
@login_required
def majors():
    majors = Major.query.all()
    return render_template('admin/majors.html', majors=majors)

@admin_bp.route('/majors/add', methods=['POST'])
@login_required
def add_major():
    data = request.get_json()
    name = data.get('name')

    if name:
        major = Major(name=name)
        db.session.add(major)
        db.session.commit()
        return jsonify({'id': major.id, 'name': major.name}), 200
    return jsonify({'error': 'Name is required'}), 400


@admin_bp.route('/majors/delete/<int:id>')
@login_required
def delete_major(id):
    major = Major.query.get_or_404(id)
    db.session.delete(major)
    db.session.commit()
    return redirect(url_for('admin.majors'))

@admin_bp.route('/majors/edit/<int:id>', methods=['POST'])
@login_required
def edit_major(id):
    major = Major.query.get_or_404(id)
    data = request.get_json()
    if data and 'name' in data:
        major.name = data['name']
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 400



# ---- Classes ----
@admin_bp.route('/classes')
def classes():
    all_classes = Class.query.all()
    class_data = []

    for cls in all_classes:
        student_count = len(cls.student_classes)
        class_data.append({
            'id': cls.id,
            'code': cls.class_code,
            'name': cls.class_name,
            'location': cls.location,
            'day': cls.day,
            'start_time': cls.class_time_start.strftime("%H:%M"),
            'end_time': cls.class_time_end.strftime("%H:%M"),
            'minimum_time': cls.minimum_attendance_minutes,
            'students': student_count
        })

    return render_template('admin/classes.html', classes=class_data)


@admin_bp.route('/classes/edit/<int:class_id>', methods=['GET'])
@login_required
def edit_class(class_id):
    class_ = Class.query.get_or_404(class_id)
    majors = Major.query.all()
    teachers = Users.query.all()
    students = Student.query.all()

    selected_students = [sc.student_nim for sc in class_.student_classes]
    assigned_teacher = AssignedClass.query.filter_by(class_id=class_id).first()

    return render_template(
        'admin/edit_class.html',
        class_=class_,
        majors=majors,
        teachers=teachers,
        students=students,
        selected_students=selected_students,
        assigned_teacher=assigned_teacher
    )
    
@admin_bp.route('/classes/update/<int:class_id>', methods=['POST'])
@login_required
def update_class(class_id):
    class_ = Class.query.get_or_404(class_id)
    old_class_name = class_.class_name
    new_class_name = request.form['class_name']

    try:
        # Update class attributes
        class_.class_code = request.form['class_code']
        class_.class_name = new_class_name
        class_.location = request.form['location']
        class_.major_id = request.form['major_id']
        class_.day = request.form['day']
        class_.class_time_start = request.form['class_time_start']
        class_.class_time_end = request.form['class_time_end']
        class_.minimum_attendance_minutes = request.form['minimum_attendance_minutes']

        # Rename folder if needed
        old_folder = os.path.join('static', 'face_snips', old_class_name)
        new_folder = os.path.join('static', 'face_snips', new_class_name)
        if os.path.exists(old_folder) and old_class_name != new_class_name:
            os.rename(old_folder, new_folder)

        # Update teacher assignment
        teacher_id = request.form['teacher_id']
        assigned_teacher = AssignedClass.query.filter_by(class_id=class_id).first()
        if assigned_teacher:
            assigned_teacher.user_id = teacher_id
        else:
            new_assignment = AssignedClass(user_id=teacher_id, class_id=class_id)
            db.session.add(new_assignment)

        # Update student assignments
        db.session.query(StudentClass).filter_by(class_id=class_id).delete()
        for student_nim in request.form.getlist('student_ids'):
            db.session.add(StudentClass(student_nim=student_nim, class_id=class_id))

        db.session.commit()
        flash('Class updated successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while updating the class: {str(e)}', 'danger')

    return redirect(url_for('admin.classes'))



@admin_bp.route('/students')
@login_required
def students():
    majors = Major.query.all()
    return render_template('admin/students.html', majors=majors)



@admin_bp.route('/add-student', methods=['POST'])
@login_required
def add_student():
    photos = request.files.getlist('photos')
    print("📸 Total uploaded photos:", len(photos))
    
    # Logging uploaded photo details
    for i, photo in enumerate(photos):
        print(f" - Photo {i+1}: filename={photo.filename}, content_type={photo.content_type}")

    # Get student data from form
    nim = request.form['nim']
    name = request.form['name']
    email = request.form['email']
    batch_year = request.form['batch_year']
    major_id = request.form['major_id']

    # Save student data to database
    new_student = Student(
        nim=nim,
        name=name,
        email=email,
        batch_year=int(batch_year),
        major_id=int(major_id)
    )
    db.session.add(new_student)
    db.session.commit()
    print(f"[ADMIN], Student added successfully!")

    # Create folder for saving images
    folder_path = os.path.join('./static', 'img_kampus', batch_year, nim)
    os.makedirs(folder_path, exist_ok=True)

    # Initialize face embedding storage
    embeddings = []
    
    # Initialize face analysis model
    face_app = FaceAnalysis(name='buffalo_l')
    face_app.prepare(ctx_id=0, det_size=(640, 640))

    # Process uploaded photos for embeddings
    for photo in photos:
        filename = secure_filename(photo.filename)
        if filename:  # Ensure filename is not empty
            save_path = os.path.join(folder_path, filename)
            photo.save(save_path)

            img = cv2.imread(save_path)
            if img is not None:
                faces = face_app.get(img)
                if faces:
                    embeddings.append(faces[0].embedding)
                else:
                    print(f"[WARNING] No face detected in image {filename}")
            else:
                print(f"[WARNING] Failed to load image {filename}")

    # Compute average embedding and save it to the database
    if embeddings:
        embeddings = np.array(embeddings)
        avg_embedding = np.mean(embeddings, axis=0)
        
        # Convert embedding to binary format for storage
        binary_embedding = avg_embedding.tobytes()

        # Update the newly created student record with the embedding
        student = Student.query.filter_by(nim=nim).first()
        if student:
            student.face_embedding = binary_embedding
            db.session.commit()
            print(f"[INFO] Saved embedding for {nim} to database.")
    
    flash('Student added successfully with face data!', 'success')
    return redirect(url_for('admin.students'))


@admin_bp.route('/delete-students-bulk', methods=['POST'])
def delete_students_bulk():
    data = request.get_json()
    nims = data.get('nims', [])
    try:
        if not nims:
            return jsonify(success=False, message="No NIMs provided.")

        # Delete related records first (StudentClass and Attendance)
        for nim in nims:
            student = Student.query.filter_by(nim=nim).first()
            if student:
                # Delete related StudentClass entries
                db.session.query(StudentClass).filter_by(student_nim=nim).delete()
                # Delete related Attendance entries
                db.session.query(Attendance).filter_by(student_id=student.id).delete()

        # Now delete the students
        Student.query.filter(Student.nim.in_(nims)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        print("Error deleting students:", e)
        return jsonify(success=False, message="Internal error.")



@admin_bp.route('/check-student', methods=['POST'])
@login_required
def check_student():
    data = request.get_json()
    nim = data.get('nim')
    email = data.get('email')

    exists_nim = Student.query.filter_by(nim=nim).first() is not None
    exists_email = Student.query.filter_by(email=email).first() is not None

    return jsonify({'exists_nim': exists_nim, 'exists_email': exists_email})

@admin_bp.route('/import-students-csv', methods=['POST'])
@login_required
def import_students_csv():
    face_app = FaceAnalysis(name='buffalo_l')
    face_app.prepare(ctx_id=0, det_size=(640, 640))
    
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.zip'):
        flash('Please upload a ZIP file containing students.csv and folders named by NIM', 'danger')
        return redirect(url_for('admin.students'))

    # Extract ZIP to temp dir
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(zip_path)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Look for students.csv
        csv_path = os.path.join(temp_dir, 'students.csv')
        if not os.path.exists(csv_path):
            flash('students.csv not found in ZIP file', 'danger')
            return redirect(url_for('admin.students'))

        # Baca dan proses CSV
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            csv_input = csv.DictReader(csvfile)
            for row in csv_input:
                try:
                    nim = row['nim'].strip()
                    batch_year = int(row['batch_year'])

                    # Simpan data ke database
                    new_student = Student(
                        nim=nim,
                        name=row['name'].strip(),
                        email=row['email'].strip(),
                        batch_year=batch_year,
                        major_id=int(row['major_id'])
                    )
                    db.session.add(new_student)

                    # Siapkan path folder foto
                    source_photo_dir = os.path.join(temp_dir, nim)
                    target_photo_dir = os.path.join(current_app.root_path, 'static', 'img_kampus', str(batch_year), nim)
                    os.makedirs(target_photo_dir, exist_ok=True)
                    
                    embeddings = []

                    print(f"[INFO] Checking folder: {source_photo_dir}")
                    if os.path.isdir(source_photo_dir):
                        for filename in os.listdir(source_photo_dir):
                            src_file = os.path.join(source_photo_dir, filename)
                            if os.path.isfile(src_file):
                                dst_file = os.path.join(target_photo_dir, secure_filename(filename))
                                shutil.copy(src_file, dst_file)

                                # Proses embedding jika bukan file 'main.jpg' (optional)
                                # if not filename.lower().startswith("main"):
                                #     img = cv2.imread(dst_file)
                                #     if img is not None:
                                #         faces = face_app.get(img)
                                #         if faces:
                                #             embeddings.append(faces[0].embedding)
                                img = cv2.imread(dst_file)
                                if img is not None:
                                    faces = face_app.get(img)
                                    if faces:
                                        embeddings.append(faces[0].embedding)
                                    else:
                                        print(f"[WARNING] No face detected in image {filename} for NIM {nim}")
                                else:
                                    print(f"[WARNING] Failed to load image {filename} for NIM {nim}")
                        print(f"[INFO] Photos copied for NIM {nim}")
                    else:
                        print(f"[WARNING] Folder not found for NIM {nim}: {source_photo_dir}")

                    # Simpan embedding ke dalam database jika ada
                    if embeddings:
                        emb_array = np.array(embeddings)
                        avg_embedding = np.mean(emb_array, axis=0)
                        
                        # Convert the numpy array to binary format
                        binary_embedding = avg_embedding.tobytes()

                        # Update the student's face_embedding in the database
                        student = Student.query.filter_by(nim=nim).first()
                        if student:
                            student.face_embedding = binary_embedding
                            print(f"[INFO] Saved embedding for {nim} to database.")
                            
                            
                    else:
                        print(f"[WARNING] No face embeddings generated for {nim}")

                except Exception as e:
                    print(f"[ERROR] Error processing student {row.get('nim', 'UNKNOWN')}: {e}")
                    continue

    db.session.commit()
    flash('Students and photos imported successfully from ZIP', 'success')
    return redirect(url_for('admin.students'))




@admin_bp.route('/api/students')
@login_required
def get_students():
    students = Student.query.join(Major).all()
    data = [{
        'nim': s.nim,
        'name': s.name,
        'email': s.email,
        'batch_year': s.batch_year,
        'major_name': s.major.name
    } for s in students]
    return jsonify({'data': data})

# @admin_bp.route('/classes/add')
# @login_required
# def add_class():
#     return render_template('admin/add_class.html')

@admin_bp.route('/add-class')
@login_required
def add_class():
    majors = Major.query.all()
    teachers = Users.query.filter_by(is_admin=False).all()
    students = Student.query.all()
    return render_template('admin/add_class.html', majors=majors, teachers=teachers, students=students)

@admin_bp.route('/save-class', methods=['POST'])
@login_required
def save_class():
    class_code = request.form.get('class_code')
    class_name = request.form.get('class_name')
    location = request.form.get('location')
    major_id = request.form.get('major_id')
    teacher_id = request.form.get('teacher_id')
    student_ids = request.form.getlist('student_ids')
    day = request.form.get('day')
    class_time_start = request.form.get('class_time_start')
    class_time_end = request.form.get('class_time_end')
    minimum_attendance_minutes = request.form.get('minimum_attendance_minutes')

    # Check if class code already exists
    if Class.query.filter_by(class_code=class_code).first():
        flash('Class code already exists.', 'danger')
        return redirect(url_for('admin.add_class'))

    try:
        # Create the class
        new_class = Class(
            class_code=class_code,
            class_name=class_name,
            location=location,
            major_id=major_id,
            day=day,
            class_time_start=class_time_start,
            class_time_end=class_time_end,
            minimum_attendance_minutes=minimum_attendance_minutes
        )
        db.session.add(new_class)
        db.session.commit()  # Commit to generate class ID

        # Assign the teacher
        assigned_teacher = AssignedClass(user_id=teacher_id, class_id=new_class.id)
        db.session.add(assigned_teacher)

        # Assign students
        for student_id in student_ids:
            student_class = StudentClass(student_nim=student_id, class_id=new_class.id)
            db.session.add(student_class)

        db.session.commit()
        flash('Class successfully created!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating class: {str(e)}', 'danger')

    return redirect(url_for('admin.classes'))


@admin_bp.route('/admin/class/delete/<int:class_id>', methods=['POST', 'GET'])
@login_required
def delete_class(class_id):
    class_ = Class.query.get(class_id)
    if not class_:
        flash('Class not found.', 'danger')
        return redirect(url_for('admin.classes'))  # Make sure this route exists

    class_folder = os.path.join('static', 'face_snips', class_.class_name)

    try:
        # Delete the folder if it exists
        if os.path.exists(class_folder):
            shutil.rmtree(class_folder)

        # Delete the class from the database
        db.session.delete(class_)
        db.session.commit()
        flash('Class and its folder deleted successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Failed to delete class. Error: {str(e)}', 'danger')

    return redirect(url_for('admin.classes'))


@admin_bp.route('/check_class', methods=['POST'])
def check_class():
    data = request.json
    class_code = data.get('class_code')
    class_name = data.get('class_name')

    response = {}

    if class_code:
        exists = Class.query.filter_by(class_code=class_code).first()
        if exists:
            response['class_code'] = 'Class code already exists.'

    if class_name:
        exists = Class.query.filter_by(class_name=class_name).first()
        if exists:
            response['class_name'] = 'Class name already exists.'

    return response, 200


def generate_mjpeg(ip_address):
    
    if isinstance(ip_address, str) and ip_address.isdigit():
        ip_address = int(ip_address)
        
    cap = cv2.VideoCapture(ip_address)
    if not cap.isOpened():
        print(f"Failed to open camera: {ip_address}")
        return

    while True:
        for _ in range(5):  # Drop stale frames
            cap.grab()

        success, frame = cap.read()
        if not success:
            continue  # Skip instead of breaking

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    

@admin_bp.route('/video_feed/<int:camera_id>')
@login_required
def video_feed(camera_id):
    camera = Camera.query.get_or_404(camera_id)
    print(f"Streaming video from camera: {camera.name} at {camera.ip_address}")
    return Response(generate_mjpeg(camera.ip_address),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
    
    
@admin_bp.route('/edit_camera/<int:camera_id>', methods=['POST'])
def edit_camera(camera_id):
    camera_id = request.form['id']  # Ambil dari form input hidden
    camera = Camera.query.get_or_404(camera_id)
    camera.name = request.form['name']
    camera.ip_address = request.form['ip_address']
    camera.location = request.form['location']
    db.session.commit()
    flash('Camera updated successfully!', 'success')
    return redirect(url_for('admin.camera'))
