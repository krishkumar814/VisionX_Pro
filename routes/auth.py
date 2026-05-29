from flask import Blueprint, render_template, redirect, url_for, request, flash
from models import db, User, Class, Subject, Assignment, Department
from flask_login import login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from ai_engine.mcq_service import MCQFactory
from models import QuestionBank, Subject

auth = Blueprint('auth', __name__)
bcrypt = Bcrypt()

# --- LOGIN ROUTE (For All Roles) ---
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            # Route to dashboard based on role
            if user.role == 'Technical Head':
                return redirect(url_for('auth.admin_dashboard'))
            elif user.role == 'Teacher':
                return redirect(url_for('teacher.dashboard'))
            elif user.role == 'Student':
                return redirect(url_for('student.dashboard'))
            elif user.role == 'HOD':
                return redirect(url_for('hod_director.dashboard'))
            elif user.role == 'Director':
                return redirect(url_for('hod_director.director_dashboard'))
            return redirect(url_for('home'))
        
        flash("Invalid credentials", "danger")
    return render_template('login.html')

# --- TECHNICAL HEAD DASHBOARD ---
@auth.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role not in ['Technical Head', 'HOD']:
        return "Access Denied", 403
    
    # 1. Fetch the data
    users = User.query.all()
    all_classes = Class.query.all() # We call it all_classes here
    subjects = Subject.query.all()
    assignments = Assignment.query.all()
    departments = Department.query.all()
    
    # 2. Pass it to the template
    # We tell Jinja2: "Inside the HTML, 'classes' will refer to 'all_classes'"
    return render_template('admin_dashboard.html', 
                           users=users, 
                           subjects=subjects, 
                           classes=all_classes, 
                           assignments=assignments,
                           departments=departments)

# --- USER REGISTRATION (Technical Head Only) ---
@auth.route('/admin/register_user', methods=['POST'])
@login_required # <--- Security Layer 1
def register_user():
    # Security Layer 2: Only Technical Head can create users
    if current_user.role != 'Technical Head':
        flash("Unauthorized access!", "danger")
        return redirect(url_for('home'))
    
    name = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    class_id = request.form.get('class_id')
    department_id = request.form.get('department_id')

    # Logic Check: Prevent Duplicate Emails
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash("Email already registered!", "warning")
        return redirect(url_for('auth.admin_dashboard'))

    # BUSINESS RULE: Only ONE Director allowed in the entire system
    if role == 'Director':
        existing_director = User.query.filter_by(role='Director').first()
        if existing_director:
            flash(f"A Director already exists ({existing_director.username}). The system only allows a single Director.", "danger")
            return redirect(url_for('auth.admin_dashboard'))

    # BUSINESS RULE: Only ONE HOD per department
    if role == 'HOD':
        if not department_id or department_id.strip() == "":
            flash("HOD must be assigned to a department.", "danger")
            return redirect(url_for('auth.admin_dashboard'))
        existing_hod = User.query.filter_by(role='HOD', department_id=int(department_id)).first()
        if existing_hod:
            flash(f"Department already has an HOD ({existing_hod.username}). Each department can only have one HOD.", "danger")
            return redirect(url_for('auth.admin_dashboard'))

    # Build user fields
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    
    final_class_id = None
    if role == 'Student' and class_id and class_id.strip() != "":
        try:
            final_class_id = int(class_id)
        except ValueError:
            final_class_id = None

    # For students, auto-inherit department from their class
    final_dept_id = None
    if role == 'Student' and final_class_id:
        student_class = db.session.get(Class, final_class_id)
        if student_class and student_class.department_id:
            final_dept_id = student_class.department_id
    elif role != 'Student' and role != 'Director':
        # Teacher/HOD get department from the form
        if department_id and department_id.strip() != "":
            try:
                final_dept_id = int(department_id)
            except ValueError:
                final_dept_id = None

    new_user = User(
        username=name,
        email=email,
        password_hash=hashed_pw,
        role=role,
        class_id=final_class_id,
        department_id=final_dept_id
    )

    db.session.add(new_user)
    db.session.commit()

    flash(f"User {name} registered successfully as {role}!", "success")
    return redirect(url_for('auth.admin_dashboard'))


@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

# --- ADD NEW CLASS ---
@auth.route('/admin/add_class', methods=['POST'])
@login_required
def add_class():
    if current_user.role != 'Technical Head':
        return "Unauthorized", 403
    
    class_name = request.form.get('class_name')
    dept_id = request.form.get('department_id')
    
    if not Class.query.filter_by(name=class_name).first():
        final_dept_id = None
        if dept_id and dept_id.strip() != "":
            try:
                final_dept_id = int(dept_id)
            except ValueError:
                final_dept_id = None
        new_class = Class(name=class_name, department_id=final_dept_id)
        db.session.add(new_class)
        db.session.commit()
        flash(f"Class {class_name} created!", "success")
    else:
        flash(f"Class {class_name} already exists.", "warning")
    return redirect(url_for('auth.admin_dashboard'))

# --- ADD NEW SUBJECT ---
@auth.route('/admin/add_subject', methods=['POST'])
@login_required
def add_subject():
    if current_user.role != 'Technical Head':
        return "Unauthorized", 403
    
    subject_name = request.form.get('subject_name')
    if not Subject.query.filter_by(name=subject_name).first():
        new_subject = Subject(name=subject_name)
        db.session.add(new_subject)
        db.session.commit()
        flash(f"Subject {subject_name} created!", "success")
    return redirect(url_for('auth.admin_dashboard'))

@auth.route('/admin/assign_teacher', methods=['POST'])
@login_required
def assign_teacher():
    if current_user.role != 'Technical Head':
        return "Unauthorized", 403
    
    t_id = request.form.get('teacher_id')
    s_id = request.form.get('subject_id')
    c_id = request.form.get('class_id')

    # Check if this specific assignment already exists
    existing = Assignment.query.filter_by(teacher_id=t_id, subject_id=s_id, class_id=c_id).first()
    
    if not existing:
        new_assign = Assignment(teacher_id=t_id, subject_id=s_id, class_id=c_id)
        db.session.add(new_assign)
        db.session.commit()
        flash("Teacher assigned successfully!", "success")
    else:
        flash("This assignment already exists.", "warning")
        
    return redirect(url_for('auth.admin_dashboard'))

# --- ADD NEW DEPARTMENT ---
@auth.route('/admin/add_department', methods=['POST'])
@login_required
def add_department():
    if current_user.role != 'Technical Head':
        return "Unauthorized", 403
    
    dept_name = request.form.get('department_name')
    if not Department.query.filter_by(name=dept_name).first():
        new_dept = Department(name=dept_name)
        db.session.add(new_dept)
        db.session.commit()
        flash(f"Department {dept_name} created!", "success")
    else:
        flash(f"Department {dept_name} already exists.", "warning")
    return redirect(url_for('auth.admin_dashboard'))

@auth.route('/admin/assign_hod_director', methods=['POST'])
@login_required
def assign_hod_director():
    if current_user.role != 'Technical Head':
        return "Unauthorized", 403
        
    dept_id = request.form.get('department_id')
    hod_id = request.form.get('hod_id')
    director_id = request.form.get('director_id')
    
    dept = Department.query.get(dept_id)
    if dept:
        if hod_id and hod_id.strip() != "":
            # Check if this department already has an HOD
            if dept.hod_id and dept.hod_id != int(hod_id):
                existing_hod = db.session.get(User, dept.hod_id)
                flash(f"Department '{dept.name}' already has an HOD ({existing_hod.username if existing_hod else 'Unknown'}). Remove the current HOD first.", "danger")
                return redirect(url_for('auth.admin_dashboard'))
            dept.hod_id = int(hod_id)
        if director_id and director_id.strip() != "":
            dept.director_id = int(director_id)
        db.session.commit()
        flash("Department roles assigned successfully!", "success")
    return redirect(url_for('auth.admin_dashboard'))

@auth.route('/hod/generate_test', methods=['POST'])
@login_required
def generate_weekly_test():
    if current_user.role != 'HOD':
        return "Unauthorized", 403

    subject_id = request.form.get('subject_id')
    topic = request.form.get('topic')
    difficulty = request.form.get('difficulty')
    
    subject = Subject.query.get(subject_id)
    
    factory = MCQFactory()
    # Trigger the Multi-Agent Loop
    validated_questions = factory.generate_test(subject.name, topic, difficulty)

    # Save to the Database QuestionBank
    for q in validated_questions:
        new_q = QuestionBank(
            subject_id=subject_id,
            question_text=q['question'],
            options=q['options'],
            correct_answer=q['answer'],
            difficulty=difficulty,
            is_validated=True # Agent B approved this
        )
        db.session.add(new_q)
    
    db.session.commit()
    flash(f"AI Agents have successfully generated and validated {len(validated_questions)} questions!", "success")
    return redirect(url_for('auth.admin_dashboard'))