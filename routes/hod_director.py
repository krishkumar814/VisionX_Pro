from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Subject, QuestionBank, TestSession, Class, Complaint, ExamPhase, MarksCorrectionRequest, User, ExamResult, Department
from services.analytics import calculate_department_kpi
from datetime import datetime
from google import genai
import os
import re

hod_director = Blueprint('hod_director', __name__)

@hod_director.route('/hod/dashboard')
@login_required
def dashboard():
    if current_user.role != 'HOD':
        return "Unauthorized", 403
        
    # LAZY AUTO-ESCALATION CHECK (15-DAY RULE)
    if current_user.department_id:
        all_pending = Complaint.query.filter_by(department_id=current_user.department_id, status='Pending').all()
    else:
        all_pending = []
        
    escalated_count = 0
    now = datetime.utcnow()
    for c in all_pending:
        if (now - c.created_at).days > 15:
            c.status = 'Escalated'
            c.assigned_to = 'Director'
            c.is_escalated_to_director = True
            c.escalation_history = (c.escalation_history or "") + f"\nAuto-escalated to Director on {now.strftime('%Y-%m-%d')}."
            escalated_count += 1
    if escalated_count > 0:
        db.session.commit()
    
    # Only fetch classes belonging to this HOD's department
    if current_user.department_id:
        classes = Class.query.filter_by(department_id=current_user.department_id).all()
        # Get subjects taught within this department via Assignments
        from models import Assignment
        dept_teacher_ids = [t.id for t in User.query.filter_by(department_id=current_user.department_id, role='Teacher').all()]
        dept_subject_ids = db.session.query(Assignment.subject_id).filter(Assignment.teacher_id.in_(dept_teacher_ids)).distinct().all()
        dept_subject_ids = [sid[0] for sid in dept_subject_ids]
        subjects = Subject.query.filter(Subject.id.in_(dept_subject_ids)).all() if dept_subject_ids else []
    else:
        classes = []
        subjects = []
    
    # Enforce strict scope: only active sessions from teachers in this HOD's department
    if current_user.department_id:
        active_weekly_sessions = TestSession.query.join(User, TestSession.teacher_id == User.id).filter(
            TestSession.quiz_type == 'Weekly',
            TestSession.is_active == True,
            User.department_id == current_user.department_id
        ).all()
    else:
        active_weekly_sessions = []
    
    if current_user.department_id:
        my_complaints = Complaint.query.filter_by(
            department_id=current_user.department_id, 
            assigned_to='HOD', 
            status='Pending'
        ).all()
        dept_kpi = calculate_department_kpi(current_user.department_id)
        active_exam_phases = ExamPhase.query.filter_by(department_id=current_user.department_id, is_active=True).all()
        exam_phases = ExamPhase.query.filter_by(department_id=current_user.department_id).all()
        correction_requests = MarksCorrectionRequest.query.join(ExamResult).join(ExamPhase).filter(
            ExamPhase.department_id == current_user.department_id,
            MarksCorrectionRequest.status == 'Pending'
        ).all()
        
        from services.analytics import calculate_teacher_performance
        teachers = User.query.filter_by(department_id=current_user.department_id, role='Teacher').all()
        teacher_performances = []
        for t in teachers:
            teacher_performances.append({
                'teacher': t,
                'kpi': calculate_teacher_performance(t.id)
            })
    else:
        my_complaints = Complaint.query.filter_by(
            assigned_to='HOD', 
            status='Pending'
        ).all()
        dept_kpi = 0
        active_exam_phases = []
        exam_phases = []
        correction_requests = []
        teacher_performances = []
    
    return render_template('hod_dashboard.html', subjects=subjects, classes=classes, active_sessions=active_weekly_sessions, complaints=my_complaints, dept_kpi=dept_kpi, active_exam_phases=active_exam_phases, exam_phases=exam_phases, correction_requests=correction_requests, teacher_performances=teacher_performances)

@hod_director.route('/hod/resolve_complaint', methods=['POST'])
@login_required
def hod_resolve_complaint():
    if current_user.role != 'HOD':
        return "Unauthorized", 403
    comp_id = request.form.get('complaint_id')
    response_text = request.form.get('hod_response')
    
    c = Complaint.query.get(comp_id)
    if c:
        c.hod_response = response_text
        c.status = 'Resolved'
        db.session.commit()
        flash("Complaint Resolved.", "success")
    return redirect(url_for('hod_director.dashboard'))

@hod_director.route('/hod/escalate_complaint/<int:comp_id>')
@login_required
def hod_escalate_complaint(comp_id):
    if current_user.role != 'HOD':
        return "Unauthorized", 403
    c = Complaint.query.get(comp_id)
    if c and c.department_id == current_user.department_id:
        if c.is_escalated_to_director or c.status == 'Resolved':
            flash("Complaint has already been finalized or escalated. Further escalation is blocked.", "danger")
        else:
            c.status = 'Escalated'
            c.assigned_to = 'Director'
            c.is_escalated_to_director = True
            c.escalation_history = (c.escalation_history or "") + "\nEscalated by HOD to Director."
            db.session.commit()
            flash("Complaint escalated directly to Director.", "warning")
    return redirect(url_for('hod_director.dashboard'))

@hod_director.route('/hod/open_exam_phase', methods=['POST'])
@login_required
def open_exam_phase():
    if current_user.role != 'HOD' or not current_user.department_id:
        return "Unauthorized", 403
    name = request.form.get('name')
    new_phase = ExamPhase(name=name, department_id=current_user.department_id, is_active=True)
    db.session.add(new_phase)
    db.session.commit()
    flash(f"Exam Phase '{name}' opened successfully.", "success")
    return redirect(url_for('hod_director.dashboard'))

@hod_director.route('/hod/close_exam_phase/<int:phase_id>')
@login_required
def close_exam_phase(phase_id):
    if current_user.role != 'HOD':
        return "Unauthorized", 403
    phase = db.session.get(ExamPhase, phase_id)
    
    # Strictly validate department scope
    if phase and phase.department_id == current_user.department_id:
        phase.is_active = False
        # Lock all marks for this phase
        results = ExamResult.query.filter_by(exam_phase_id=phase_id).all()
        for r in results:
            r.is_locked = True
        db.session.commit()
        flash("Exam phase closed. Marks are now locked.", "warning")
    else:
        flash("Unauthorized action or phase not found.", "danger")
    return redirect(url_for('hod_director.dashboard'))

@hod_director.route('/hod/handle_correction/<int:req_id>/<action>', methods=['POST'])
@login_required
def handle_correction(req_id, action):
    if current_user.role != 'HOD':
        return "Unauthorized", 403
    
    req = db.session.get(MarksCorrectionRequest, req_id)
    if not req:
        return "Not found", 404
        
    hod_response = request.form.get('hod_response')
    
    if action == 'approve':
        req.status = 'Approved'
        req.hod_response = hod_response
        req.exam_result.marks_obtained = req.new_marks
        req.exam_result.is_locked = True # Ensure it stays locked
        flash("Correction approved and marks updated.", "success")
    elif action == 'reject':
        req.status = 'Rejected'
        req.hod_response = hod_response
        flash("Correction rejected.", "danger")
        
    db.session.commit()
    return redirect(url_for('hod_director.dashboard'))

@hod_director.route('/director/dashboard')
@login_required
def director_dashboard():
    if current_user.role != 'Director':
        return "Unauthorized", 403
        
    # Director sees ALL escalated complaints regardless of their own department_id
    my_complaints = Complaint.query.filter_by(
        assigned_to='Director', 
        status='Escalated'
    ).all()
        
    from services.analytics import calculate_department_kpi, calculate_department_attendance
    departments = Department.query.all()
    dept_stats = []
    for d in departments:
        dept_stats.append({
            'department': d,
            'kpi': calculate_department_kpi(d.id),
            'attendance': calculate_department_attendance(d.id),
            'students': User.query.filter_by(department_id=d.id, role='Student').count(),
            'teachers': User.query.filter_by(department_id=d.id, role='Teacher').count()
        })
        
    return render_template('director_dashboard.html', complaints=my_complaints, dept_stats=dept_stats)

@hod_director.route('/director/resolve_complaint', methods=['POST'])
@login_required
def dir_resolve_complaint():
    if current_user.role != 'Director':
        return "Unauthorized", 403
    comp_id = request.form.get('complaint_id')
    response_text = request.form.get('hod_response')
    c = Complaint.query.get(comp_id)
    if c:
        c.hod_response = "DIRECTOR FINAL RESOLUTION: " + response_text
        c.status = 'Resolved'
        # Once it's resolved by director, it is completely finalized.
        db.session.commit()
        flash("Escalated grievance formally resolved and permanently locked.", "success")
    return redirect(url_for('hod_director.director_dashboard'))

@hod_director.route('/director/department_drilldown/<int:dept_id>')
@login_required
def department_drilldown(dept_id):
    if current_user.role != 'Director':
        return "Unauthorized", 403
        
    department = Department.query.get_or_404(dept_id)
    
    from services.analytics import calculate_teacher_performance, calculate_department_kpi
    teachers = User.query.filter_by(department_id=dept_id, role='Teacher').all()
    teacher_performances = []
    for t in teachers:
        teacher_performances.append({
            'teacher': t,
            'kpi': calculate_teacher_performance(t.id)
        })
        
    dept_kpi = calculate_department_kpi(dept_id)
        
    return render_template('director_dept_drilldown.html', department=department, teacher_performances=teacher_performances, dept_kpi=dept_kpi)

@hod_director.route('/hod/teacher_drilldown/<int:teacher_id>')
@login_required
def teacher_drilldown(teacher_id):
    if current_user.role not in ['HOD', 'Director']:
        return "Unauthorized", 403
        
    teacher = User.query.get_or_404(teacher_id)
    if current_user.role == 'HOD' and teacher.department_id != current_user.department_id:
        return "Unauthorized", 403
    if teacher.role != 'Teacher':
        return "Unauthorized", 403
        
    from models import Assignment, ExamResult
    assignments = Assignment.query.filter_by(teacher_id=teacher_id).all()
    
    # We will pass the assignments to the template. The template will use an AJAX endpoint
    # to fetch the chart data for a selected assignment, similar to the Teacher dashboard.
    
    return render_template('hod_teacher_drilldown.html', teacher=teacher, assignments=assignments)

@hod_director.route('/hod/chart_data', methods=['GET'])
@login_required
def chart_data():
    if current_user.role != 'HOD':
        return {"error": "Unauthorized"}, 403
        
    class_id = request.args.get('class_id')
    subject_id = request.args.get('subject_id')
    teacher_id = request.args.get('teacher_id')
    
    if not class_id or not subject_id or not teacher_id:
        return {"labels": [], "data": []}
        
    teacher = User.query.get(teacher_id)
    if not teacher or teacher.department_id != current_user.department_id:
        return {"error": "Unauthorized"}, 403
        
    students = User.query.filter_by(class_id=class_id, role='Student').all()
    labels = []
    data = []
    
    from models import ExamResult, AttendanceRecord
    
    for s in students:
        labels.append(s.username)
        results = ExamResult.query.filter_by(student_id=s.id, subject_id=subject_id).all()
        total_marks = sum(r.marks_obtained for r in results)
        max_marks = sum(r.max_marks for r in results)
        marks_pct = (total_marks / max_marks * 100) if max_marks > 0 else 0
        
        total_att = AttendanceRecord.query.filter_by(student_id=s.id, subject_id=subject_id).count()
        present_att = AttendanceRecord.query.filter_by(student_id=s.id, subject_id=subject_id, status='Present').count()
        att_pct = (present_att / total_att * 100) if total_att > 0 else 0
        
        if max_marks > 0 and total_att > 0:
            subject_kpi = (marks_pct * 0.7) + (att_pct * 0.3)
        elif max_marks > 0:
            subject_kpi = marks_pct
        elif total_att > 0:
            subject_kpi = att_pct
        else:
            subject_kpi = 0
            
        data.append(round(subject_kpi, 1))
        
    return {"labels": labels, "data": data}

@hod_director.route('/hod/stop_test/<int:session_id>')
@login_required
def stop_weekly_test(session_id):
    if current_user.role != 'HOD':
        return "Unauthorized", 403
    session = TestSession.query.get(session_id)
    if session:
        session.is_active = False
        db.session.commit()
    return redirect(url_for('hod_director.dashboard'))

@hod_director.route('/hod/api/subjects_by_class/<int:class_id>')
@login_required
def api_subjects_by_class(class_id):
    """Return subjects taught in a specific class within the HOD's department."""
    if current_user.role != 'HOD':
        return {"error": "Unauthorized"}, 403
    from models import Assignment
    # Get teachers in this HOD's department
    dept_teacher_ids = [t.id for t in User.query.filter_by(department_id=current_user.department_id, role='Teacher').all()]
    # Get subjects assigned to this class by department teachers
    subject_ids = db.session.query(Assignment.subject_id).filter(
        Assignment.class_id == class_id,
        Assignment.teacher_id.in_(dept_teacher_ids)
    ).distinct().all()
    subject_ids = [sid[0] for sid in subject_ids]
    subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all() if subject_ids else []
    return {"subjects": [{"id": s.id, "name": s.name} for s in subjects]}

@hod_director.route('/generate_weekly_test', methods=['POST'])
@login_required
def generate_weekly_test():
    if current_user.role not in ['HOD', 'Director']:
        return "Unauthorized", 403

    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id')
    topic = request.form.get('topic')
    difficulty = request.form.get('difficulty')

    subject = Subject.query.get(subject_id)
    
    try:
        api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyDjkWPZNbX8Cf6r6MgF5DaysRQ0qttxxJE')
        client = genai.Client(api_key=api_key)
        
        prompt = f"Generate 5 MCQs for {subject.name} on {topic}. Format: Q: [text] A: [text] B: [text] C: [text] D: [text] Correct: [Letter]"
        
        new_session = TestSession(
            class_id=class_id,
            subject_id=subject_id,
            teacher_id=current_user.id,
            quiz_type="Weekly",
            topics=topic,
            is_active=True
        )
        db.session.add(new_session)
        db.session.flush()

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw_text = response.text
        blocks = raw_text.split('Q:')[1:] 
        
        count = 0
        for block in blocks:
            content = "Q:" + block
            
            q_text = re.search(r'Q:\s*(.*?)(?=A:|$)', content, re.DOTALL)
            a_text = re.search(r'A:\s*(.*?)(?=B:|$)', content, re.DOTALL)
            b_text = re.search(r'B:\s*(.*?)(?=C:|$)', content, re.DOTALL)
            c_text = re.search(r'C:\s*(.*?)(?=D:|$)', content, re.DOTALL)
            d_text = re.search(r'D:\s*(.*?)(?=Correct:|$)', content, re.DOTALL)
            ans_match = re.search(r'Correct:\s*([A-D])|Correct:.*?(A|B|C|D)', content, re.IGNORECASE)

            if q_text and a_text and b_text and c_text and d_text and ans_match:
                q_val = q_text.group(1).strip()
                opts_list = [
                    "A: " + a_text.group(1).strip().replace('\n', ' '),
                    "B: " + b_text.group(1).strip().replace('\n', ' '),
                    "C: " + c_text.group(1).strip().replace('\n', ' '),
                    "D: " + d_text.group(1).strip().replace('\n', ' ')
                ]
                
                ans_letter = ans_match.group(1) if ans_match.group(1) else ans_match.group(2)
                ans_letter = ans_letter.upper()
                
                correct_val = ""
                for opt in opts_list:
                    if opt.startswith(ans_letter + ":"):
                        correct_val = opt.split(':', 1)[1].strip()

                if not correct_val:
                    correct_val = ans_letter

                new_q = QuestionBank(
                    subject_id=subject_id,
                    session_id=new_session.id,
                    question_text=q_val,
                    options="|||".join(opts_list),
                    correct_answer=correct_val,
                    difficulty=difficulty
                )
                db.session.add(new_q)
                count += 1

        db.session.commit()
        flash(f"Weekly Test Live! {count} questions added.", "success")        
    except Exception as e:
        db.session.rollback()
        flash(f"AI Error: {str(e)}", "danger")

    return redirect(url_for('hod_director.dashboard'))