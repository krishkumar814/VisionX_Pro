from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

# 1. USER & ROLE MANAGEMENT
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=True)
    
    # We rename the relationship to be unique
    # 'back_populates' is the modern, safer way to link two sides
    assigned_class = db.relationship('Class', back_populates='students')
    
    credits = db.Column(db.Integer, default=0)
    attendance_percentage = db.Column(db.Float, default=0.0)

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    hod_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    director_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    hod = db.relationship('User', foreign_keys=[hod_id])
    director = db.relationship('User', foreign_keys=[director_id])

# 2. ACADEMIC STRUCTURE
class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    
    # This links back to the 'assigned_class' in the User model
    students = db.relationship('User', back_populates='assigned_class', lazy=True)
    department = db.relationship('Department')

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # This one line creates 'subject.materials' AND 'material.subject' automatically
    materials = db.relationship('StudyMaterial', backref='subject', lazy=True)
# 3. THE "JOIN" TABLE (Teacher -> Subject -> Class)
class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'))

    teacher = db.relationship('User', foreign_keys=[teacher_id])
    subject = db.relationship('Subject')
    
    # Adding 'overlaps' prevents the warning you saw in the logs
    target_class = db.relationship('Class', overlaps="assignments,my_class")
# 4. CONTENT & AI TESTING
class StudyMaterial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(200), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))

    # FIX: Remove the manual 'subject =' line and just keep the teacher link.
    # We will use backref for the subject link to avoid the collision.
    teacher = db.relationship('User', backref='materials_uploaded')
    
    # This line below was likely causing the crash because 'Subject' 
    # already has a relationship pointing here. 
    # REMOVE OR COMMENT OUT THIS LINE:
    # subject = db.relationship('Subject', backref='materials')

class QuestionBank(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))
    session_id = db.Column(db.Integer, db.ForeignKey('test_session.id'), nullable=True)
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False) # Store as list: ["A", "B", "C", "D"]
    correct_answer = db.Column(db.String(10))
    difficulty = db.Column(db.String(20)) # Easy, Medium, Hard
    is_validated = db.Column(db.Boolean, default=False) # Multi-agent check

class TestSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    quiz_type = db.Column(db.String(50), default="Weekly")
    topics = db.Column(db.String(255), nullable=False)
    remarks = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    target_class = db.relationship('Class')
    subject = db.relationship('Subject')
    teacher = db.relationship('User', foreign_keys=[teacher_id])
    assigned_student = db.relationship('User', foreign_keys=[assigned_student_id])

class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('test_session.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)


# 5. ADAPTIVE LEARNING (Learn New)
class Roadmap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tech_name = db.Column(db.String(50)) # e.g., "React"
    sections = db.Column(db.JSON) # JSON roadmap structure

class StudentProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tech_id = db.Column(db.Integer, db.ForeignKey('roadmap.id'))
    current_section = db.Column(db.Integer, default=1)
    is_completed = db.Column(db.Boolean, default=False)

# 6. FEEDBACK & GOVERNANCE
class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    secret_token = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Escalated, Resolved, Reopened
    assigned_to = db.Column(db.String(20), default='HOD') # HOD, Director
    hod_response = db.Column(db.Text, nullable=True)
    is_escalated_to_director = db.Column(db.Boolean, default=False)
    escalation_history = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    department = db.relationship('Department')
    student = db.relationship('User', foreign_keys=[student_id])

class PerformanceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    predicted_label = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('User', foreign_keys=[student_id])

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    status = db.Column(db.String(20), nullable=False) # 'Present', 'Absent'

class TeacherNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    teacher = db.relationship('User', foreign_keys=[teacher_id])

class ChatQueryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    query = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('User', foreign_keys=[student_id])

# 7. EXAM & EVALUATION
class ExamPhase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # e.g. "Mid-Term", "End-Sem"
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship('Department')

class ExamResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    exam_phase_id = db.Column(db.Integer, db.ForeignKey('exam_phase.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    marks_obtained = db.Column(db.Float, nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    is_submitted = db.Column(db.Boolean, default=False)
    is_locked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', foreign_keys=[student_id])
    subject = db.relationship('Subject')
    exam_phase = db.relationship('ExamPhase')
    teacher = db.relationship('User', foreign_keys=[teacher_id])

class MarksCorrectionRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_result_id = db.Column(db.Integer, db.ForeignKey('exam_result.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    new_marks = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    hod_response = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exam_result = db.relationship('ExamResult')
    teacher = db.relationship('User', foreign_keys=[teacher_id])