from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, User, Assignment, Subject, Class, StudyMaterial, TestSession, QuestionBank, AttendanceRecord, Roadmap, StudentProgress, TeacherNotification, ExamPhase, ExamResult, MarksCorrectionRequest
from flask_login import login_required, current_user
import os
import re
import json
from datetime import datetime
from google import genai
import os
from werkzeug.utils import secure_filename

def clean_json_response(res):
    text = res.strip()
    if text.startswith('```json'):
        text = text[7:]
    if text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    return text.strip()
def generate_ai_questions(subject_id, topics, num_q, session_id=None, difficulty="Medium", progressive=False):
    """Reusable function to fetch questions from Gemini and save to DB"""
    try:
        subject = db.session.get(Subject, subject_id)
        api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyDjkWPZNbX8Cf6r6MgF5DaysRQ0qttxxJE')
        client = genai.Client(api_key=api_key)
        
        if progressive:
            prompt = f"Generate {num_q} MCQs for {subject.name} on the weak topic: {topics}. Start with Easy difficulty and progressively enhance the level up to Hard. Format: Q: [text] A: [text] B: [text] C: [text] D: [text] Correct: [Letter]"
        else:
            prompt = f"""
            Generate {num_q} MCQs for {subject.name} specifically on these topics: {topics}.
            Difficulty: {difficulty}.
            Format: Q: [text] A: [text] B: [text] C: [text] D: [text] Correct: [Letter]
            """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        blocks = response.text.split('Q:')[1:] 
        
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

                new_q = QuestionBank(
                    subject_id=subject_id,
                    session_id=session_id,
                    question_text=q_val,
                    options="|||".join(opts_list),
                    correct_answer=correct_val if correct_val else ans_letter,
                    difficulty=difficulty
                )
                db.session.add(new_q)
        db.session.commit()
        return True
    except Exception as e:
        print(f"AI Error: {e}")
        return False
    
teacher = Blueprint('teacher', __name__)



@teacher.route('/teacher/dashboard')
@login_required
def dashboard():
    if current_user.role != 'Teacher':
        return "Unauthorized", 403

    # Fetch all assignments for this specific teacher
    my_assignments = Assignment.query.filter_by(teacher_id=current_user.id).all()
    
    # Get distinct classes and subjects for the upload dropdowns
    assigned_classes = Class.query.join(Assignment).filter(Assignment.teacher_id == current_user.id).all()
    assigned_subjects = Subject.query.join(Assignment).filter(Assignment.teacher_id == current_user.id).all()

    class_ids = [c.id for c in assigned_classes]
    my_students = User.query.filter(User.class_id.in_(class_ids), User.role == 'Student').all() if class_ids else []

    filter_class = request.args.get('class_id')
    filter_subject = request.args.get('subject_id')
    filter_student = request.args.get('student_id')

    # Query Active Sessions
    sessions_query = TestSession.query.filter_by(teacher_id=current_user.id, is_active=True)
    if filter_subject:
        sessions_query = sessions_query.filter_by(subject_id=filter_subject)
    if filter_student:
        sessions_query = sessions_query.filter_by(assigned_student_id=filter_student)
    if filter_class:
        sessions_query = sessions_query.join(User, TestSession.assigned_student_id == User.id).filter(User.class_id == filter_class)
    active_sessions = sessions_query.all()

    # Query Notifications
    notifications = TeacherNotification.query.filter_by(teacher_id=current_user.id, is_read=False).order_by(TeacherNotification.created_at.desc()).all()
    if filter_student:
        student = db.session.get(User, filter_student)
        if student:
            notifications = [n for n in notifications if student.username in n.message]
    elif filter_class:
        students_in_class = User.query.filter_by(class_id=filter_class, role='Student').all()
        student_names = [s.username for s in students_in_class]
        notifications = [n for n in notifications if any(name in n.message for name in student_names)]

    active_exam_phases = ExamPhase.query.filter_by(department_id=current_user.department_id, is_active=True).all() if current_user.department_id else []
    
    total_students = len(set(s.id for s in my_students))
    avg_attendance = 0
    if total_students > 0:
        avg_attendance = sum(s.attendance_percentage for s in my_students) / total_students
    
    from services.analytics import calculate_teacher_performance
    teacher_kpi = calculate_teacher_performance(current_user.id)

    # Subject Performance Chart Data (Aggregate KPI per Subject)
    subject_marks = {}
    for a in my_assignments:
        subject_name = a.subject.name
        if subject_name not in subject_marks:
            subject_marks[subject_name] = []
        # Calculate subject-wise KPI by averaging the KPIs of students in this subject/class
        students_in_class = User.query.filter_by(class_id=a.class_id, role='Student').all()
        from services.analytics import calculate_student_kpi
        for s in students_in_class:
            subject_marks[subject_name].append(calculate_student_kpi(s.id))
        
    subject_labels = []
    subject_averages = []
    for sub, kpis in subject_marks.items():
        subject_labels.append(sub)
        subject_averages.append(round(sum(kpis) / len(kpis), 1) if kpis else 0)
        
    if not subject_labels:
        subject_labels = ['No Data']
        subject_averages = [0]
        
    # Check if all drafts are done for active exam phases
    all_drafts_done = False
    if active_exam_phases:
        # Require marks for all assigned subjects & classes
        all_drafts_done = True
        for phase in active_exam_phases:
            for assignment in my_assignments:
                class_students = User.query.filter_by(class_id=assignment.class_id, role='Student').all()
                for student in class_students:
                    res = ExamResult.query.filter_by(
                        student_id=student.id,
                        subject_id=assignment.subject_id,
                        exam_phase_id=phase.id
                    ).first()
                    if not res:
                        all_drafts_done = False
                        break
                if not all_drafts_done:
                    break
            if not all_drafts_done:
                break

    return render_template('teacher_dashboard.html', 
                           assignments=my_assignments,
                           classes=assigned_classes,
                           subjects=assigned_subjects,
                           my_students=my_students,
                           active_sessions=active_sessions,
                           notifications=notifications,
                           active_exam_phases=active_exam_phases,
                           total_students=total_students,
                           avg_attendance=round(avg_attendance, 2),
                           teacher_kpi=teacher_kpi,
                           subject_labels=subject_labels,
                           subject_averages=subject_averages,
                           all_drafts_done=all_drafts_done)

@teacher.route('/teacher/upload', methods=['POST'])
@login_required
def upload_material():
    if current_user.role != 'Teacher':
        return "Unauthorized", 403

    file = request.files.get('file')
    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id') # Metadata for which class can see this
    title = request.form.get('title')

    if file and subject_id:
        filename = secure_filename(file.filename)
        # Create subject-specific folder for organization
        upload_path = os.path.join('static/uploads', f"subject_{subject_id}")
        if not os.path.exists(upload_path):
            os.makedirs(upload_path)
            
        file_path = os.path.join(upload_path, filename)
        file.save(file_path)

        new_material = StudyMaterial(
            title=title,
            file_path=file_path,
            subject_id=subject_id,
            teacher_id=current_user.id
        )
        db.session.add(new_material)
        db.session.commit()
        
        # NOTE: This is where we will later trigger the AI to index the PDF
        flash(f"Material '{title}' uploaded successfully!", "success")
        
    return redirect(url_for('teacher.dashboard'))

@teacher.route('/teacher/start_test', methods=['POST'])
@login_required
def start_test():
    subject_id = request.form.get('subject_id')
    student_id = request.form.get('student_id')
    remarks = request.form.get('remarks')
    num_q = request.form.get('num_questions', 5)

    # 1. Ask AI to extract a concise topic name from remarks
    try:
        api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyAYGoiSvjb-V5Mc31Bybc0XrwIaS4PIu3M')
        client = genai.Client(api_key=api_key)
        topic_extract_prompt = f"Based on the following teacher remarks about a student's weakness, provide ONLY a concise 2-4 word topic title (e.g., 'SQL Joins', 'Backpropagation', 'Pointers'). Remarks: {remarks}"
        extracted_topics = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=topic_extract_prompt
        ).text.strip()
    except Exception as e:
        print("Failed to extract topic", e)
        extracted_topics = "General Assistance"

    # Calculate Adaptive Difficulty based on past performance
    from models import QuizAttempt
    past_attempts = QuizAttempt.query.join(TestSession).filter(
        TestSession.subject_id == subject_id, 
        QuizAttempt.student_id == student_id
    ).all()
    
    if past_attempts:
        avg_score = sum(a.score for a in past_attempts) / len(past_attempts)
        percentage = (avg_score / int(num_q)) * 100 if int(num_q) > 0 else 50
        if percentage < 50:
            adaptive_diff = "Easy"
        elif percentage <= 80:
            adaptive_diff = "Medium"
        else:
            adaptive_diff = "Hard"
    else:
        adaptive_diff = "Medium"

    # Create the session with remarks
    new_session = TestSession(
        subject_id=subject_id,
        teacher_id=current_user.id,
        assigned_student_id=student_id,
        quiz_type="Weak Topic",
        topics=extracted_topics,
        remarks=remarks,
        is_active=True
    )
    db.session.add(new_session)
    db.session.flush() # get ID without committing to true DB transaction

    # Call the function we just created using the extracted topics and adaptive difficulty
    ai_success = generate_ai_questions(subject_id, extracted_topics, num_q, session_id=new_session.id, difficulty=adaptive_diff, progressive=False)

    if ai_success:
        # Generate the learning roadmap for the weak topic based on REMARKS
        tech_name = f"Weak Topic: {new_session.id}"
        try:
            api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyAYGoiSvjb-V5Mc31Bybc0XrwIaS4PIu3M')
            client = genai.Client(api_key=api_key)
            prompt = f"""
            A teacher provided these remarks about a student: '{remarks}'.
            Generate a 5-level learning roadmap to help the student improve based exactly on these remarks.
            Include a title, description, an array of 'topics', and 'gfg_link' and 'youtube_link'. 
            Return strictly VALID JSON format.
            Format: [{{"level": 1, "title": "...", "description": "...", "topics": ["..."], "gfg_link": "...", "youtube_link": "..."}}]
            """
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            sections = json.loads(clean_json_response(response.text))
            roadmap = Roadmap(tech_name=tech_name, sections=sections)
            db.session.add(roadmap)
            db.session.flush()
            
            prog = StudentProgress(student_id=student_id, tech_id=roadmap.id, current_section=1)
            db.session.add(prog)
        except Exception as e:
            print("Failed to generate Weak Topic Roadmap: ", e)

        db.session.commit()
        flash(f"Test and Roadmap are now LIVE based on your remarks!", "success")
    else:
        db.session.rollback()
        flash("Failed to generate AI questions. Check API key.", "danger")

    return redirect(url_for('teacher.dashboard'))

@teacher.route('/teacher/update_roadmap/<int:session_id>', methods=['POST'])
@login_required
def update_roadmap(session_id):
    new_remarks = request.form.get('new_remarks')
    session = TestSession.query.get(session_id)
    if not session or session.teacher_id != current_user.id:
        return "Unauthorized", 403

    # Update remarks log in DB
    if session.remarks:
        session.remarks += f"\n\nUpdate: {new_remarks}"
    else:
        session.remarks = new_remarks
        
    tech_name = f"Weak Topic: {session.id}"
    roadmap = Roadmap.query.filter_by(tech_name=tech_name).first()
    
    if roadmap:
        try:
            api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyAYGoiSvjb-V5Mc31Bybc0XrwIaS4PIu3M')
            client = genai.Client(api_key=api_key)
            prompt = f"""
            Here is a student's current JSON learning roadmap for a weak topic:
            {json.dumps(roadmap.sections)}
            
            The teacher just provided these new remarks: "{new_remarks}".
            
            TASK: Mutate the JSON roadmap. 
            If the remarks indicate the student has mastered a topic, REMOVE that topic/level. 
            If new weaknesses are mentioned, ADD new levels/topics. 
            Keep the "level" integers sequential (1, 2, 3...).
            Ensure exactly the same JSON schema is returned. No markdown wrappers.
            """
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            new_sections = json.loads(clean_json_response(response.text))
            
            # Re-assign elements
            roadmap.sections = new_sections
            db.session.commit()
            
            # Create a notification back to teacher for confirmation
            notif = TeacherNotification(teacher_id=current_user.id, message=f"AI Agent successfully updated roadmap for {session.assigned_student.username} based on your new remarks.")
            db.session.add(notif)
            db.session.commit()
            flash("Roadmap dynamically adjusted!", "success")
        except Exception as e:
            print("Failed to update roadmap: ", e)
            flash("AI failed to alter the roadmap. Try again later.", "danger")
    else:
        flash("Roadmap not found for this session.", "danger")
        
    return redirect(url_for('teacher.dashboard'))

@teacher.route('/teacher/mark_notification_read/<int:notif_id>')
@login_required
def mark_notification_read(notif_id):
    if current_user.role != 'Teacher':
        return "Unauthorized", 403
    n = TeacherNotification.query.get(notif_id)
    if n and n.teacher_id == current_user.id:
        n.is_read = True
        db.session.commit()
    return redirect(url_for('teacher.dashboard'))
@teacher.route('/teacher/stop_test/<int:session_id>')
def stop_test(session_id):
    session = TestSession.query.get(session_id)
    session.is_active = False
    db.session.commit()
    return redirect(url_for('teacher.dashboard'))

@teacher.route('/teacher/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    if current_user.role != 'Teacher':
        return "Unauthorized", 403

    date_str = request.form.get('date')
    assignment_id = request.form.get('assignment_id')
    
    if not date_str or not assignment_id:
        flash("Date and Class/Subject selection are required.", "danger")
        return redirect(url_for('teacher.dashboard'))
        
    try:
        att_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date format.", "warning")
        return redirect(url_for('teacher.dashboard'))

    assignment = db.session.get(Assignment, int(assignment_id))
    if not assignment or assignment.teacher_id != current_user.id:
        flash("Invalid assignment.", "danger")
        return redirect(url_for('teacher.dashboard'))

    students = User.query.filter_by(class_id=assignment.class_id, role='Student').all()
    count = 0
    updated_students = set()
    
    for student in students:
        status = request.form.get(f'attendance_{student.id}')
        if status in ['Present', 'Absent']:
            # Check if record already exists for this date, subject, student
            record = AttendanceRecord.query.filter_by(
                student_id=student.id,
                subject_id=assignment.subject_id,
                date=att_date
            ).first()
            
            if record:
                record.status = status
                record.teacher_id = current_user.id
            else:
                record = AttendanceRecord(
                    student_id=student.id,
                    teacher_id=current_user.id,
                    class_id=assignment.class_id,
                    subject_id=assignment.subject_id,
                    date=att_date,
                    status=status
                )
                db.session.add(record)
            count += 1
            updated_students.add(student)

    if count > 0:
        db.session.commit()
        # Compile overarching attendance percentage
        for student in updated_students:
            total_records = AttendanceRecord.query.filter_by(student_id=student.id).count()
            present_records = AttendanceRecord.query.filter_by(student_id=student.id, status='Present').count()
            if total_records > 0:
                student.attendance_percentage = round((present_records / total_records) * 100, 1)
        db.session.commit()
        flash(f"Successfully saved {count} attendance records for {assignment.target_class.name} - {assignment.subject.name}.", "success")
    else:
        flash("No attendance updates were made.", "warning")
        
    return redirect(url_for('teacher.dashboard'))

@teacher.route('/teacher/get_students_for_class/<int:class_id>')
@login_required
def get_students_for_class(class_id):
    if current_user.role != 'Teacher':
        return {"error": "Unauthorized"}, 403
        
    subject_id = request.args.get('subject_id')
    phase_id = request.args.get('phase_id')
    
    assignment = Assignment.query.filter_by(teacher_id=current_user.id, class_id=class_id, subject_id=subject_id).first()
    if not assignment:
        return {"students": []}
        
    students = User.query.filter_by(class_id=class_id, role='Student').all()
    data = []
    for s in students:
        existing = ExamResult.query.filter_by(student_id=s.id, subject_id=subject_id, exam_phase_id=phase_id).first()
        data.append({
            "id": s.id,
            "username": s.username,
            "existing_mark": existing.marks_obtained if existing else None
        })
        
    return {"students": data}

@teacher.route('/teacher/bulk_upload_marks', methods=['POST'])
@login_required
def bulk_upload_marks():
    if current_user.role != 'Teacher':
        return "Unauthorized", 403

    exam_phase_id = request.form.get('exam_phase_id')
    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id')
    max_marks = request.form.get('max_marks', 100)

    phase = db.session.get(ExamPhase, exam_phase_id)
    if not phase or not phase.is_active:
        flash("Exam phase is closed or invalid. Marks cannot be uploaded or edited.", "danger")
        return redirect(url_for('teacher.dashboard'))

    if phase.department_id != current_user.department_id:
        flash("Unauthorized action: Scope mismatch.", "danger")
        return redirect(url_for('teacher.dashboard'))

    # Validate assignment
    assignment = Assignment.query.filter_by(teacher_id=current_user.id, subject_id=subject_id, class_id=class_id).first()
    if not assignment:
        flash("You are not assigned to this subject and class.", "danger")
        return redirect(url_for('teacher.dashboard'))

    students = User.query.filter_by(class_id=class_id, role='Student').all()
    
    count = 0
    for student in students:
        mark_val = request.form.get(f'marks_{student.id}')
        if mark_val and mark_val.strip() != "":
            try:
                marks_obtained = float(mark_val)
                max_m = float(max_marks)
                
                existing = ExamResult.query.filter_by(
                    student_id=student.id, 
                    subject_id=subject_id, 
                    exam_phase_id=exam_phase_id
                ).first()
                
                if existing:
                    if not existing.is_submitted:
                        existing.marks_obtained = marks_obtained
                        existing.max_marks = max_m
                        count += 1
                else:
                    new_result = ExamResult(
                        student_id=student.id,
                        subject_id=subject_id,
                        exam_phase_id=exam_phase_id,
                        teacher_id=current_user.id,
                        marks_obtained=marks_obtained,
                        max_marks=max_m,
                        is_submitted=False
                    )
                    db.session.add(new_result)
                    count += 1
            except ValueError:
                pass

    if count > 0:
        db.session.commit()
        flash(f"Draft marks saved successfully for {count} students.", "success")
    else:
        flash("No valid marks were entered.", "warning")
        
    return redirect(url_for('teacher.dashboard'))

@teacher.route('/teacher/submit_all_marks', methods=['POST'])
@login_required
def submit_all_marks():
    if current_user.role != 'Teacher':
        return "Unauthorized", 403
        
    # Mark all unsubmitted results as submitted
    results = ExamResult.query.filter_by(teacher_id=current_user.id, is_submitted=False).all()
    for r in results:
        r.is_submitted = True
    db.session.commit()
    
    flash("All marks have been officially submitted to the HOD.", "success")
    return redirect(url_for('teacher.dashboard'))

@teacher.route('/teacher/api/correction_students', methods=['GET'])
@login_required
def correction_students_api():
    """Fetch students with their latest exam phase results for a class/subject."""
    if current_user.role != 'Teacher':
        return jsonify({"error": "Unauthorized"}), 403

    class_id = request.args.get('class_id', type=int)
    subject_id = request.args.get('subject_id', type=int)

    if not class_id or not subject_id:
        return jsonify({"error": "Class and Subject are required."}), 400

    # Verify teacher is assigned to this class/subject
    assignment = Assignment.query.filter_by(teacher_id=current_user.id, class_id=class_id, subject_id=subject_id).first()
    if not assignment:
        return jsonify({"error": "You are not assigned to this class/subject."}), 403

    # Find the LATEST (most recent) exam phase for teacher's department
    latest_phase = ExamPhase.query.filter_by(department_id=current_user.department_id).order_by(ExamPhase.created_at.desc()).first()
    if not latest_phase:
        return jsonify({"error": "No exam phases found.", "students": []})

    # Get results for this phase, class, and subject
    results = ExamResult.query.filter_by(
        exam_phase_id=latest_phase.id,
        subject_id=subject_id,
        teacher_id=current_user.id
    ).join(User, ExamResult.student_id == User.id).filter(
        User.class_id == class_id
    ).all()

    students = []
    for r in results:
        students.append({
            "result_id": r.id,
            "student_id": r.student_id,
            "student_name": r.student.username,
            "marks_obtained": r.marks_obtained,
            "max_marks": r.max_marks,
        })

    return jsonify({
        "phase_name": latest_phase.name,
        "students": students
    })


@teacher.route('/teacher/request_correction', methods=['POST'])
@login_required
def request_correction():
    if current_user.role != 'Teacher':
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    corrections = data.get('corrections', [])
    reason = data.get('reason', '').strip()

    if not corrections:
        return jsonify({"error": "No corrections provided."}), 400
    if not reason:
        return jsonify({"error": "Reason is required."}), 400

    created = 0
    skipped = 0
    for c in corrections:
        exam_result_id = c.get('exam_result_id')
        new_marks = c.get('new_marks')

        result = db.session.get(ExamResult, exam_result_id)
        if not result or result.teacher_id != current_user.id:
            continue

        try:
            new_marks = float(new_marks)
        except (ValueError, TypeError):
            continue

        # Skip if pending request already exists
        existing = MarksCorrectionRequest.query.filter_by(
            exam_result_id=exam_result_id,
            status='Pending'
        ).first()
        if existing:
            skipped += 1
            continue

        req = MarksCorrectionRequest(
            exam_result_id=exam_result_id,
            teacher_id=current_user.id,
            reason=reason,
            new_marks=new_marks
        )
        db.session.add(req)
        created += 1

    db.session.commit()

    if created == 0 and skipped > 0:
        return jsonify({"error": f"All {skipped} correction(s) already have pending requests."}), 400

    msg = f"{created} correction request(s) submitted to HOD."
    if skipped > 0:
        msg += f" {skipped} skipped (already pending)."
    return jsonify({"success": True, "message": msg})

@teacher.route('/teacher/chart_data', methods=['GET'])
@login_required
def chart_data():
    if current_user.role != 'Teacher':
        return {"error": "Unauthorized"}, 403
        
    class_id = request.args.get('class_id')
    subject_id = request.args.get('subject_id')
    
    if not class_id or not subject_id:
        return {"labels": [], "data": []}
        
    assignment = Assignment.query.filter_by(teacher_id=current_user.id, class_id=class_id, subject_id=subject_id).first()
    if not assignment:
        return {"labels": [], "data": []}
        
    students = User.query.filter_by(class_id=class_id, role='Student').all()
    labels = []
    data = []
    from services.analytics import calculate_student_kpi
    
    for s in students:
        labels.append(s.username)
        # Ideally, we calculate student KPI for THIS specific subject. For now, use overall KPI or subject-specific marks.
        # But we can calculate subject-specific KPI here:
        # We need marks, attendance, etc. for this subject.
        from models import ExamResult, AttendanceRecord
        
        # 1. Marks
        results = ExamResult.query.filter_by(student_id=s.id, subject_id=subject_id).all()
        total_marks = sum(r.marks_obtained for r in results)
        max_marks = sum(r.max_marks for r in results)
        marks_pct = (total_marks / max_marks * 100) if max_marks > 0 else 0
        
        # 2. Attendance
        total_att = AttendanceRecord.query.filter_by(student_id=s.id, subject_id=subject_id).count()
        present_att = AttendanceRecord.query.filter_by(student_id=s.id, subject_id=subject_id, status='Present').count()
        att_pct = (present_att / total_att * 100) if total_att > 0 else 0
        
        # Simple weighted sum (or simple average for this specific subject drill-down)
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