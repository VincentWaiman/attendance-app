from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import LargeBinary

db = SQLAlchemy()

class Users(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Major(db.Model):
    __tablename__ = 'majors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    classes = db.relationship('Class', back_populates='major', cascade='all, delete')
    students = db.relationship('Student', back_populates='major', cascade='all, delete')

class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    class_code = db.Column(db.String(20), unique=True, nullable=False)
    class_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=True)

    major_id = db.Column(db.Integer, db.ForeignKey('majors.id'), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    class_time_start = db.Column(db.Time, nullable=False)
    class_time_end = db.Column(db.Time, nullable=False)
    
    minimum_attendance_minutes = db.Column(db.Integer, nullable=False, default=0)

    major = db.relationship('Major', back_populates='classes')
    student_classes = db.relationship('StudentClass', back_populates='class_', cascade='all, delete')
    schedules = db.relationship('Schedule', back_populates='class_', cascade='all, delete')
    assigned_users = db.relationship('AssignedClass', back_populates='class_', cascade='all, delete')


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    nim = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    batch_year = db.Column(db.Integer, nullable=False)  # Year of admission
    major_id = db.Column(db.Integer, db.ForeignKey('majors.id'), nullable=False)
    face_embedding = db.Column(LargeBinary, nullable=True)

    major = db.relationship('Major', back_populates='students')
    student_classes = db.relationship('StudentClass', back_populates='student', cascade='all, delete')
    attendances = db.relationship('Attendance', back_populates='student', cascade='all, delete')


class StudentClass(db.Model):
    __tablename__ = 'student_classes'
    id = db.Column(db.Integer, primary_key=True)
    student_nim = db.Column(db.String(20), db.ForeignKey('students.nim'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)

    student = db.relationship('Student', back_populates='student_classes', primaryjoin='Student.nim == StudentClass.student_nim')
    class_ = db.relationship('Class', back_populates='student_classes')

class Schedule(db.Model):
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    tanggal = db.Column(db.String(20), nullable=False)  # ganti 'date' jadi 'tanggal'
    is_validate = db.Column(db.Boolean, default=False)  # tambahkan kolom validasi

    class_ = db.relationship('Class', back_populates='schedules')
    attendances = db.relationship('Attendance', back_populates='schedule', cascade='all, delete')

class Attendance(db.Model):
    __tablename__ = 'attendances'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=False)
    timestamp = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Present')
    label = db.Column(db.String(50))

    student = db.relationship('Student', back_populates='attendances')
    schedule = db.relationship('Schedule', back_populates='attendances')

class Camera(db.Model):
    __tablename__ = 'cameras'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)

class AssignedClass(db.Model):
    __tablename__ = 'assigned_classes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)

    user = db.relationship('Users', backref='assigned_classes')
    class_ = db.relationship('Class', back_populates='assigned_users')
    
    
    
    