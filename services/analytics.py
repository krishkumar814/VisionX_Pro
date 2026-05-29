from models import User, ExamResult, QuizAttempt, AttendanceRecord, Department, db, Assignment

def calculate_student_kpi(student_id):
    """
    Calculates KPI normalized to 100 for a student.
    - Academic (Exam Marks): 40%
    - Engagement (Attendance): 30%
    - Activity (Quizzes): 20%
    - Improvement: 10%
    """
    student = db.session.get(User, student_id)
    if not student:
        return 0.0

    # 1. Academic Performance (Exam Results)
    exams = ExamResult.query.filter_by(student_id=student_id).all()
    if exams:
        total_obtained = sum(e.marks_obtained for e in exams)
        total_max = sum(e.max_marks for e in exams)
        academic_score = (total_obtained / total_max * 100) if total_max > 0 else 0
    else:
        academic_score = 0 # Default if no exams taken yet
        
    # 2. Engagement (Attendance)
    engagement_score = student.attendance_percentage if student.attendance_percentage else 0.0

    # 3. Activity (Quiz Attempts) & Improvement
    quizzes = QuizAttempt.query.filter_by(student_id=student_id).order_by(QuizAttempt.attempted_at.asc()).all()
    if quizzes:
        avg_score = sum(q.score for q in quizzes) / len(quizzes)
        # Normalize score. Assume a quiz is out of 5 usually. Cap at 100.
        activity_score = min(avg_score * 20, 100) 
        
        # Improvement: compare second half of quizzes vs first half
        mid = len(quizzes) // 2
        if mid > 0:
            first_half_avg = sum(q.score for q in quizzes[:mid]) / mid
            second_half_avg = sum(q.score for q in quizzes[mid:]) / (len(quizzes) - mid)
            
            # Improvement ratio (1.0 = 50 score, 1.5 = 100 score, 0.5 = 0 score)
            if first_half_avg > 0:
                imp = (second_half_avg / first_half_avg)
                imp_score = min(max((imp - 0.5) * 100, 0), 100)
            else:
                imp_score = 100 if second_half_avg > 0 else 50
        else:
            imp_score = 50 # Baseline if only 1 quiz taken
    else:
        activity_score = 0
        imp_score = 0
        
    # Weighting: 40% Academic, 30% Engagement, 20% Activity, 10% Improvement
    if not exams and not quizzes:
        kpi = engagement_score
    elif not exams:
        kpi = (engagement_score * 0.6) + (activity_score * 0.3) + (imp_score * 0.1)
    else:
        kpi = (academic_score * 0.4) + (engagement_score * 0.3) + (activity_score * 0.2) + (imp_score * 0.1)
        
    return round(kpi, 2)

def calculate_teacher_performance(teacher_id):
    """
    Teacher performance based on their students' KPIs in their assigned subjects.
    For simplicity, average of student KPIs they teach.
    """
    assignments = Assignment.query.filter_by(teacher_id=teacher_id).all()
    class_ids = [a.class_id for a in assignments]
    
    if not class_ids:
        return 0.0
        
    students = User.query.filter(User.class_id.in_(class_ids), User.role == 'Student').all()
    if not students:
        return 0.0
        
    total_kpi = sum(calculate_student_kpi(s.id) for s in students)
    return round(total_kpi / len(students), 2)

def calculate_department_kpi(department_id):
    """
    Department KPI is the average of all its students' KPIs.
    """
    students = User.query.filter_by(department_id=department_id, role='Student').all()
    if not students:
        return 0.0
        
    total_kpi = sum(calculate_student_kpi(s.id) for s in students)
    return round(total_kpi / len(students), 2)

def calculate_department_attendance(department_id):
    """
    Department Attendance is the average of all its students' attendance percentages.
    """
    students = User.query.filter_by(department_id=department_id, role='Student').all()
    if not students:
        return 0.0
        
    total_att = sum(s.attendance_percentage for s in students if s.attendance_percentage)
    return round(total_att / len(students), 1)
