from flask import Blueprint, render_template, request, flash, redirect, url_for
from models import db, User, StudyMaterial, Subject, Assignment, Class, Complaint, Department, TeacherNotification, ExamResult
from flask_login import login_required, current_user
from ai_engine.chat_service import SubjectAgent
from models import QuestionBank, TestSession, QuizAttempt, Roadmap, StudentProgress, PerformanceHistory
import string, random
import json
import re
from google import genai
import os

student = Blueprint('student', __name__)

from services.ml_service import predict_student_performance, get_recommendations

@student.route('/student/dashboard')
@login_required
def dashboard():
    if current_user.role != 'Student':
        return "Unauthorized", 403
        
    predicted_performance = predict_student_performance(current_user.id)

    # 1. Get all subjects assigned to this student's specific class
    # We look at the Assignment table to see which subjects are linked to current_user.class_id
    my_assignments = Assignment.query.filter_by(class_id=current_user.class_id).all()
    
    # Extract unique subjects from these assignments
    my_subjects = []
    subject_ids = set()
    for assign in my_assignments:
        if assign.subject_id not in subject_ids:
            my_subjects.append(assign.subject)
            subject_ids.add(assign.subject_id)

    # Fetch active quizzes not yet attempted
    active_sessions = TestSession.query.filter(
        (TestSession.is_active == True) &
        ((TestSession.class_id == current_user.class_id) | (TestSession.assigned_student_id == current_user.id))
    ).all()
    
    unattempted_weekly_quizzes = []
    unattempted_practice_quizzes = []
    for session in active_sessions:
        already_done = QuizAttempt.query.filter_by(
            student_id=current_user.id, 
            session_id=session.id
        ).first()
        if not already_done:
            if session.quiz_type == "Weekly":
                unattempted_weekly_quizzes.append(session)
            else:
                unattempted_practice_quizzes.append(session)

    # Detect Weak Topics based on past quiz scores (percentage < 50%)
    weak_topics = []
    all_attempts = QuizAttempt.query.filter_by(student_id=current_user.id).order_by(QuizAttempt.attempted_at.desc()).all()
    for attempt in all_attempts:
        session = db.session.get(TestSession, attempt.session_id)
        if session and session.topics:
            total_qs = QuestionBank.query.filter_by(session_id=session.id).count()
            if total_qs == 0:
                total_qs = 5 # fallback
                
            percentage = (attempt.score / total_qs) * 100
            
            if percentage < 50:
                # Prevent duplicate topics by checking if already in list
                if not any(wt['topic'] == session.topics for wt in weak_topics):
                    weak_topics.append({
                        'subject': session.subject.name,
                        'topic': session.topics,
                        'score': attempt.score,
                        'percentage': round(percentage, 1),
                        'subject_id': session.subject_id,
                        'session_id': session.id
                    })

    recommendations = get_recommendations(predicted_performance, weak_topics=weak_topics)

    # Log Performance
    last_log = PerformanceHistory.query.filter_by(student_id=current_user.id).order_by(PerformanceHistory.timestamp.desc()).first()
    if not last_log or last_log.predicted_label != predicted_performance:
        new_log = PerformanceHistory(student_id=current_user.id, predicted_label=predicted_performance)
        db.session.add(new_log)
        db.session.commit()

    # Fetch historical quiz scores for trend chart
    recent_attempts = QuizAttempt.query.filter_by(student_id=current_user.id).order_by(QuizAttempt.attempted_at.asc()).all()
    marks_trend_data = [a.score * 20 for a in recent_attempts[-6:]] if recent_attempts else []
    marks_trend_labels = [f"Quiz {i+1}" for i in range(len(marks_trend_data))]

    from services.analytics import calculate_student_kpi
    student_kpi = calculate_student_kpi(current_user.id)

    return render_template('student_dashboard.html', 
                           subjects=my_subjects, 
                           user=current_user,
                           unattempted_weekly_quizzes=unattempted_weekly_quizzes,
                           unattempted_practice_quizzes=unattempted_practice_quizzes,
                           predicted_performance=predicted_performance,
                           recommendations=recommendations,
                           weak_topics=weak_topics,
                           student_kpi=student_kpi,
                           marks_trend_data=marks_trend_data,
                           marks_trend_labels=marks_trend_labels)

@student.route('/student/subject/<int:subject_id>')
@login_required
def view_subject(subject_id):
    if current_user.role != 'Student':
        return "Unauthorized", 403

    subject = Subject.query.get_or_404(subject_id)
    
    # Only show materials for this subject that were uploaded for the student's class
    # (In a more advanced version, we'd filter StudyMaterial by class_id too)
    materials = StudyMaterial.query.filter_by(subject_id=subject_id).all()
    
    # Fetch phase-wise exam results
    exam_results = ExamResult.query.filter_by(student_id=current_user.id, subject_id=subject_id).all()
    
    return render_template('subject_view.html', 
                           subject=subject, 
                           materials=materials,
                           exam_results=exam_results)

@student.route('/student/chat', methods=['POST'])
@login_required
def chat_with_ai():
    data = request.json
    user_query = data.get('message')
    sub_id = data.get('subject_id')
    mat_id = data.get('material_id')
    
    subject = Subject.query.get(sub_id)
    
    from ai_engine.chat_service import SubjectAgent
    
    try:
        from models import ChatQueryLog
        log = ChatQueryLog(student_id=current_user.id, query=user_query)
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Failed to log chat query: {e}")

    try:
        agent = SubjectAgent()
        if mat_id:
            mat = StudyMaterial.query.get(mat_id)
            if mat and mat.file_path:
                answer = agent.ask_document_mode(user_query, subject.name, mat.file_path)
            else:
                answer = agent.ask_general_mode(user_query, subject.name)
        else:
            answer = agent.ask_general_mode(user_query, subject.name)
    except Exception as e:
        print(f"Chatbot failed: {e}")
        answer = "I'm sorry, I'm experiencing high traffic right now. Please try your question again in a moment."
    
    return {"answer": answer}

@student.route('/student/take_test/<int:subject_id>')
@login_required
def take_test(subject_id):
    session_id_arg = request.args.get('session_id', type=int)
    session = None
    
    if session_id_arg:
        # Load specifically requested session from notification
        session = db.session.get(TestSession, session_id_arg)
        if session and session.subject_id != subject_id:
            session = None
            
    if not session:
        # Fallback: Find an active session for the student's class (Weekly) OR student's assigned (Weak Topic)
        all_active_sessions = TestSession.query.filter(
            (TestSession.subject_id == subject_id) &
            (TestSession.is_active == True) &
            ((TestSession.class_id == current_user.class_id) | (TestSession.assigned_student_id == current_user.id))
        ).all()
        
        # Prioritize finding an *unattempted* session
        for s in all_active_sessions:
            already_done = QuizAttempt.query.filter_by(
                student_id=current_user.id, 
                session_id=s.id
            ).first()
            if not already_done:
                session = s
                break
                
        # If all were attempted, just set to the first one to trigger the already done logic
        if not session and all_active_sessions:
            session = all_active_sessions[0]

    if not session:
        flash("No active test for this subject right now.", "warning")
        return redirect(url_for('student.dashboard'))

    # Check if student already gave the test
    already_done = QuizAttempt.query.filter_by(
        student_id=current_user.id, 
        session_id=session.id
    ).first()
    
    if already_done:
        flash("You have already submitted this test!", "danger")
        return redirect(url_for('student.dashboard'))

    # Fetch ONLY questions generated for this specific session/topics
    questions = QuestionBank.query.filter_by(session_id=session.id).limit(5).all()
    if not questions:
        # Fallback for old tests created before the session_id update
        questions = QuestionBank.query.filter_by(subject_id=subject_id).order_by(QuestionBank.id.desc()).limit(5).all()
    
    subject = Subject.query.get_or_404(subject_id)
    return render_template('take_test.html', questions=questions, subject=subject, session_id=session.id)
@student.route('/student/submit_test', methods=['POST'])
@login_required
def submit_test():
    score = 0
    total_questions = 0
    
    for key, user_answer in request.form.items():
        if key.startswith('q_'):
            total_questions += 1
            question_id = int(key.split('_')[1])
            q_obj = db.session.get(QuestionBank, question_id)
            
            if q_obj:
                def clean(text):
                    text = str(text).lower().strip()
                    if ":" in text:
                        text = text.split(":", 1)[1].strip()
                    return text

                clean_user = clean(user_answer)
                clean_correct = clean(q_obj.correct_answer)

                # --- ADD THE DEBUG LINE HERE ---
                print(f"DEBUG Check Q{question_id}: User said '{clean_user}' | Correct is '{clean_correct}'")

                if clean_user == clean_correct:
                    score += 1
                    print("DEBUG Result: MATCH")
                else:
                    print("DEBUG Result: MISMATCH")

    # Save score and update credits
    session_id = request.form.get('session_id')
    session_obj = db.session.get(TestSession, session_id)
    reward = 0

    if session_obj and session_obj.quiz_type == "Weekly":
        reward = score * 20
        current_user.credits += reward

    new_attempt = QuizAttempt(student_id=current_user.id, session_id=session_id, score=score)
    db.session.add(new_attempt)

    msg_type = "Weekly Quiz!"
    if session_obj and session_obj.quiz_type == "Weak Topic":
        msg_type = "Weak Topic Quiz!"
        # Create a notification for the teacher
        notif_msg = f"Student {current_user.username} completed MCQ for Weak Topic '{session_obj.topics}' with score {score}/{total_questions}."
        teacher_id = session_obj.teacher_id
        new_notif = TeacherNotification(teacher_id=teacher_id, message=notif_msg)
        db.session.add(new_notif)

    db.session.commit()
    
    flash(f"{msg_type} Scored {score}/{total_questions}. Earned {reward} Credits!", "success")
    return redirect(url_for('student.dashboard'))

@student.route('/student/leaderboard')
@login_required
def leaderboard():
    if current_user.role != 'Student':
        return "Unauthorized", 403
    
    # Get students from the same class, sorted by credits descending, top 5
    students = User.query.filter_by(role='Student', class_id=current_user.class_id)\
                         .order_by(User.credits.desc())\
                         .limit(5).all()
    
    return render_template('leaderboard.html', students=students)

@student.route('/student/complaints')
@login_required
def complaints_portal():
    if current_user.role != 'Student':
        return "Unauthorized", 403
    my_complaints = Complaint.query.filter_by(student_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    return render_template('student_complaints.html', tracked_complaint=None, my_complaints=my_complaints)

@student.route('/student/submit_complaint', methods=['POST'])
@login_required
def submit_complaint():
    if current_user.role != 'Student':
        return "Unauthorized", 403
        
    complaint_text = request.form.get('complaint_text')
    
    # AI Content Filter Pipeline
    try:
        api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyAYGoiSvjb-V5Mc31Bybc0XrwIaS4PIu3M')
        client = genai.Client(api_key=api_key)
        prompt = f"Assess if the following text contains any profanity, swear words, hate speech, explicit content, or abusive language. Return strictly VALID if it is a professional grievance, or INVALID if it contains any swear words (e.g., 'fuck', 'shit'), toxicity, or abuse, regardless of the context: '{complaint_text}'"
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        assessment = response.text.strip().upper()
        
        if "INVALID" in assessment:
            flash("Complaint blocked. AI Moderator detected explicit or abusive language.", "danger")
            return redirect(url_for('student.complaints_portal'))
    except Exception as e:
        print(f"AI Moderation Failed or Blocked by Safety: {e}")
        flash("Complaint blocked. Your text triggered our AI Safety explicit content filters.", "danger")
        return redirect(url_for('student.complaints_portal'))

    # Token Generation
    secret_token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    # Retrieve student's department_id via their class or direct mapping
    student_class = db.session.get(Class, current_user.class_id)
    # The department must be inferred. Since we didn't strictly map Class -> Dept in MVP,
    # let's fallback to the student's department_id (if set) or find a generic fallback.
    # We added `department_id` to `User` in models! We assume `current_user.department_id` is set.
    dept_id = current_user.department_id
    if not dept_id:
        # Fallback safeguard
        first_dept = Department.query.first()
        dept_id = first_dept.id if first_dept else 1

    new_comp = Complaint(
        secret_token=secret_token,
        department_id=dept_id,
        text=complaint_text,
        status='Pending',
        assigned_to='HOD',
        student_id=current_user.id
    )
    db.session.add(new_comp)
    db.session.commit()
    
    flash(f"Complaint submitted anonymously! Save this Secret Token to track it: {secret_token}", "success")
    return redirect(url_for('student.complaints_portal'))

@student.route('/student/track_complaint', methods=['POST'])
@login_required
def track_complaint():
    token = request.form.get('secret_token', '').strip()
    c = Complaint.query.filter_by(secret_token=token).first()
    
    if not c:
        flash("Invalid Token or Complaint not found.", "danger")
        return redirect(url_for('student.complaints_portal'))
        
    my_complaints = Complaint.query.filter_by(student_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    return render_template('student_complaints.html', tracked_complaint=c, my_complaints=my_complaints)

@student.route('/student/reopen_complaint/<token>', methods=['POST'])
@login_required
def reopen_complaint(token):
    c = Complaint.query.filter_by(secret_token=token).first()
    # Backend Finality Check
    if c and c.status == 'Resolved':
        if c.is_escalated_to_director or (c.hod_response and "DIRECTOR FINAL RESOLUTION:" in c.hod_response):
            flash("This complaint has been permanently locked by the Director. No further escalations are allowed.", "danger")
        else:
            c.status = 'Escalated'
            c.assigned_to = 'Director'
            c.is_escalated_to_director = True
            c.escalation_history = (c.escalation_history or "") + "\nReopened and Escalated by Student to Director."
            db.session.commit()
            flash("Your complaint has been forcefully Reopened and Escalated directly to the Department Director.", "success")
    my_complaints = Complaint.query.filter_by(student_id=current_user.id).order_by(Complaint.created_at.desc()).all()
    return render_template('student_complaints.html', tracked_complaint=c, my_complaints=my_complaints)

# ----------------- LEARN NEW MODULE -----------------

def clean_json_response(res):
    """Helper to extract JSON from GenAI response which might have markdown fences."""
    text = res.strip()
    if text.startswith('```json'):
        text = text[7:]
    if text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    return text.strip()

@student.route('/student/learn_new', methods=['GET', 'POST'])
@login_required
def learn_new_dashboard():
    if request.method == 'POST':
        tech_name = request.form.get('tech_name', '').strip()
        if not tech_name:
            flash("Please enter a technology name.", "danger")
            return redirect(url_for('student.learn_new_dashboard'))
            
        # Check if roadmap exists globally
        roadmap = Roadmap.query.filter(Roadmap.tech_name.ilike(tech_name)).first()
        if not roadmap:
            # Generate new roadmap via AI
            try:
                api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyAYGoiSvjb-V5Mc31Bybc0XrwIaS4PIu3M')
                client = genai.Client(api_key=api_key)
                prompt = f"""
                Generate a 5-level learning roadmap for {tech_name}. 
                Include a title, description (as an intro), an array of specific 'topics', and highly relevant exact URLs for 'gfg_link' (GeeksforGeeks) and 'youtube_link' for each level. 
                Return strictly VALID JSON format without any markdown wrappers or text outside the JSON.
                Format: 
                [
                  {{"level": 1, "title": "Introduction...", "description": "Intro to this section...", "topics": ["topic 1", "topic 2", "topic 3"], "gfg_link": "https://www.geeksforgeeks.org/...", "youtube_link": "https://youtube.com/..."}},
                  ...
                ]
                """
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                json_str = clean_json_response(response.text)
                
                try:
                    sections = json.loads(json_str)
                except json.JSONDecodeError:
                    print(f"Failed to parse AI JSON response: {json_str}")
                    flash("AI Error: The generated roadmap format was invalid. Please try again.", "danger")
                    return redirect(url_for('student.learn_new_dashboard'))
                
                roadmap = Roadmap(tech_name=tech_name, sections=sections)
                db.session.add(roadmap)
                db.session.commit()
            except Exception as e:
                print("Failed to generate Roadmap: ", e)
                flash("AI Error: Could not generate roadmap right now. Try again later.", "danger")
                return redirect(url_for('student.learn_new_dashboard'))
                
        # Check if student already enrolled
        prog = StudentProgress.query.filter_by(student_id=current_user.id, tech_id=roadmap.id).first()
        if not prog:
            prog = StudentProgress(student_id=current_user.id, tech_id=roadmap.id, current_section=1)
            db.session.add(prog)
            db.session.commit()
            flash(f"Successfully started Learning Path: {roadmap.tech_name}", "success")
            
        return redirect(url_for('student.view_roadmap', roadmap_id=roadmap.id))
        
    paths = db.session.query(StudentProgress, Roadmap).join(Roadmap).filter(StudentProgress.student_id == current_user.id).all()
    return render_template('learn_new.html', paths=paths)

@student.route('/student/learn/<int:roadmap_id>')
@login_required
def view_roadmap(roadmap_id):
    prog = StudentProgress.query.filter_by(student_id=current_user.id, tech_id=roadmap_id).first()
    if not prog:
        return redirect(url_for('student.learn_new_dashboard'))
        
    roadmap = Roadmap.query.get_or_404(roadmap_id)
    return render_template('roadmap_view.html', roadmap=roadmap, progress=prog)

@student.route('/student/learn/<int:roadmap_id>/test')
@login_required
def take_roadmap_test(roadmap_id):
    prog = StudentProgress.query.filter_by(student_id=current_user.id, tech_id=roadmap_id).first()
    roadmap = Roadmap.query.get_or_404(roadmap_id)
    if not prog or prog.is_completed:
        return redirect(url_for('student.learn_new_dashboard'))
        
    active_section = None
    for sec in roadmap.sections:
        if sec.get('level') == prog.current_section:
            active_section = sec
            break
            
    if not active_section:
        flash("Section not found.", "warning")
        return redirect(url_for('student.view_roadmap', roadmap_id=roadmap_id))

    # Generate 3 Questions
    try:
        api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyDjkWPZNbX8Cf6r6MgF5DaysRQ0qttxxJE')
        client = genai.Client(api_key=api_key)
        seed = random.randint(1000, 9999)
        prompt = f"""
        Generate 5 multiple choice questions for the topic '{active_section['title']}' (Level {prog.current_section} of {roadmap.tech_name}).
        Random seed: {seed}.
        Return strictly VALID JSON format. No markdown, no extra text.
        Format:
        [
          {{"question_text": "...", "options": ["Option 1 Text", "Option 2 Text", "Option 3 Text", "Option 4 Text"], "correct_answer": "exactly matching string of the correct option text"}},
          ...
        ]
        """
        resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        json_str = clean_json_response(resp.text)
        questions = json.loads(json_str)
    except Exception as e:
        print("Failed to generate gate test: ", e)
        flash("AI Error: We are having trouble generating the test right now. Try again.", "danger")
        return redirect(url_for('student.view_roadmap', roadmap_id=roadmap_id))

    return render_template('roadmap_test.html', roadmap=roadmap, section=active_section, questions=questions)

@student.route('/student/learn/<int:roadmap_id>/submit_test', methods=['POST'])
@login_required
def submit_roadmap_test(roadmap_id):
    prog = StudentProgress.query.filter_by(student_id=current_user.id, tech_id=roadmap_id).first()
    roadmap = Roadmap.query.get_or_404(roadmap_id)
    if not prog:
        return redirect(url_for('student.learn_new_dashboard'))

    score = 0
    total = int(request.form.get('total_qs', 3))
    
    for i in range(1, total + 1):
        user_ans = request.form.get(f'q_{i}', '').strip().lower()
        correct_ans = request.form.get(f'correct_{i}', '').strip().lower()
        if user_ans and correct_ans and (user_ans == correct_ans or user_ans in correct_ans or correct_ans in user_ans):
            score += 1

    if score == total:
        prog.current_section += 1
        if prog.current_section > len(roadmap.sections):
            prog.is_completed = True
            flash(f"Congratulations! You completed the {roadmap.tech_name} learning path!", "success")
        else:
            flash(f"Passed! Section {prog.current_section} is now unlocked.", "success")
            
        # Check if this roadmap is a weak topic. We prefixed them with "Weak Topic:"
        if roadmap.tech_name.startswith("Weak Topic:"):
            try:
                session_id_str = roadmap.tech_name.split("Weak Topic: ")[1].strip()
                session_obj = TestSession.query.get(int(session_id_str))
            except:
                session_obj = None
                
            if session_obj:
                try:
                    api_key = os.environ.get('GEMINI_API_KEY', 'AIzaSyAYGoiSvjb-V5Mc31Bybc0XrwIaS4PIu3M')
                    client = genai.Client(api_key=api_key)
                    prompt = f"The student {current_user.username} just passed section {prog.current_section - 1} of an AI-generated learning roadmap based on your initial remarks: '{session_obj.remarks}'. Generate a very concise 1-2 sentence professional progress report for the teacher notifying them of this milestone. No markdown."
                    report_resp = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt
                    )
                    report = report_resp.text.strip()
                except Exception as e:
                    print("AI report failed", e)
                    report = f"Student {current_user.username} passed Section {prog.current_section - 1} based on your remarks."
                    
                db.session.add(TeacherNotification(teacher_id=session_obj.teacher_id, message=report))
                    
        db.session.commit()
    else:
        flash(f"You scored {score}/{total}. You need 100% to pass. Please review the material and try again. Don't worry, a new test will be generated!", "danger")
        
    return redirect(url_for('student.view_roadmap', roadmap_id=roadmap_id))