from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, User, Department, Class, Subject, Assignment, ExamResult, AttendanceRecord
from services.analytics import calculate_department_kpi, calculate_teacher_performance, calculate_student_kpi, calculate_department_attendance

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/api/analytics/drilldown', methods=['GET'])
@login_required
def drilldown():
    view_role = request.args.get('view_role')
    dept_id = request.args.get('dept_id', type=int)
    teacher_id = request.args.get('teacher_id', type=int)
    class_id = request.args.get('class_id', type=int)
    subject_id = request.args.get('subject_id', type=int)
    
    # 1. Security & Scope Enforcement
    if current_user.role == 'Teacher' and view_role == 'teacher':
        # Only block if teacher_id is explicitly provided AND doesn't match
        if teacher_id and teacher_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
    elif current_user.role == 'HOD' and view_role in ['teacher', 'hod']:
        if dept_id and current_user.department_id != dept_id:
            return jsonify({"error": "Unauthorized"}), 403
        if teacher_id:
            teacher = db.session.get(User, teacher_id)
            if not teacher or teacher.department_id != current_user.department_id:
                return jsonify({"error": "Unauthorized"}), 403
    elif current_user.role != 'Director' and view_role == 'director':
        return jsonify({"error": "Unauthorized"}), 403

    labels = []
    data = []
    attendance_data = []
    items = []

    try:
        # LEVEL: DIRECTOR BASE (Departments)
        if view_role == 'director' and not dept_id:
            departments = Department.query.all()
            for d in departments:
                kpi = calculate_department_kpi(d.id)
                att = calculate_department_attendance(d.id)
                labels.append(d.name)
                data.append(kpi)
                attendance_data.append(att)
                items.append({"id": d.id, "name": d.name})
                
        # LEVEL: HOD BASE / DIRECTOR->DEPT (Teachers)
        elif (view_role == 'hod' and not teacher_id) or (view_role == 'director' and dept_id and not teacher_id):
            target_dept = dept_id if dept_id else current_user.department_id
            teachers = User.query.filter_by(department_id=target_dept, role='Teacher').all()
            for t in teachers:
                kpi = calculate_teacher_performance(t.id)
                att = _calc_teacher_attendance(t.id)
                labels.append(t.username)
                data.append(kpi)
                attendance_data.append(att)
                items.append({"id": t.id, "name": t.username})
                
        # LEVEL: TEACHER BASE / HOD->TEACHER / DIRECTOR->DEPT->TEACHER (Classes)
        elif (view_role == 'teacher' and not class_id) or (teacher_id and not class_id):
            target_teacher = teacher_id if teacher_id else current_user.id
            assignments = Assignment.query.filter_by(teacher_id=target_teacher).all()
            class_map = {} # class_id -> [subject_ids]
            for a in assignments:
                if a.class_id not in class_map:
                    class_map[a.class_id] = []
                class_map[a.class_id].append(a.subject_id)
                
            for cid, sub_ids in class_map.items():
                cls = db.session.get(Class, cid)
                if not cls: continue
                students = User.query.filter_by(class_id=cid, role='Student').all()
                class_kpi_total = 0
                class_att_total = 0
                count = 0
                for s in students:
                    for sid in sub_ids:
                        class_kpi_total += _calc_subject_kpi(s.id, sid)
                        class_att_total += _calc_subject_attendance(s.id, sid)
                        count += 1
                avg_kpi = round((class_kpi_total / count), 1) if count > 0 else 0
                avg_att = round((class_att_total / count), 1) if count > 0 else 0
                labels.append(cls.name)
                data.append(avg_kpi)
                attendance_data.append(avg_att)
                items.append({"id": cls.id, "name": cls.name})
                
        # LEVEL: CLASS (Subjects)
        elif class_id and not subject_id:
            target_teacher = teacher_id if teacher_id else current_user.id
            assignments = Assignment.query.filter_by(teacher_id=target_teacher, class_id=class_id).all()
            for a in assignments:
                students = User.query.filter_by(class_id=class_id, role='Student').all()
                sub_kpi_total = 0
                sub_att_total = 0
                for s in students:
                    sub_kpi_total += _calc_subject_kpi(s.id, a.subject_id)
                    sub_att_total += _calc_subject_attendance(s.id, a.subject_id)
                count = len(students)
                avg_kpi = round((sub_kpi_total / count), 1) if count > 0 else 0
                avg_att = round((sub_att_total / count), 1) if count > 0 else 0
                labels.append(a.subject.name)
                data.append(avg_kpi)
                attendance_data.append(avg_att)
                items.append({"id": a.subject.id, "name": a.subject.name})
                
        # LEVEL: SUBJECT (Students)
        elif class_id and subject_id:
            students = User.query.filter_by(class_id=class_id, role='Student').all()
            for s in students:
                kpi = _calc_subject_kpi(s.id, subject_id)
                att = _calc_subject_attendance(s.id, subject_id)
                labels.append(s.username)
                data.append(kpi)
                attendance_data.append(att)
                items.append({"id": s.id, "name": s.username})

    except Exception as e:
        print("Analytics Drilldown Error:", e)
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Server error", "details": str(e)}), 500

    return jsonify({"labels": labels, "data": data, "attendance_data": attendance_data, "items": items})


# ---- Helper Functions ---- #

def _calc_subject_kpi(student_id, subject_id):
    """Calculate a student's KPI for a specific subject."""
    results = ExamResult.query.filter_by(student_id=student_id, subject_id=subject_id).all()
    total_marks = sum(r.marks_obtained for r in results)
    max_marks = sum(r.max_marks for r in results)
    marks_pct = (total_marks / max_marks * 100) if max_marks > 0 else 0
    
    total_att = AttendanceRecord.query.filter_by(student_id=student_id, subject_id=subject_id).count()
    present_att = AttendanceRecord.query.filter_by(student_id=student_id, subject_id=subject_id, status='Present').count()
    att_pct = (present_att / total_att * 100) if total_att > 0 else 0
    
    if max_marks > 0 and total_att > 0:
        return round((marks_pct * 0.7) + (att_pct * 0.3), 1)
    elif max_marks > 0:
        return round(marks_pct, 1)
    elif total_att > 0:
        return round(att_pct, 1)
    return 0

def _calc_subject_attendance(student_id, subject_id):
    """Calculate a student's attendance percentage for a specific subject."""
    total_att = AttendanceRecord.query.filter_by(student_id=student_id, subject_id=subject_id).count()
    present_att = AttendanceRecord.query.filter_by(student_id=student_id, subject_id=subject_id, status='Present').count()
    return round((present_att / total_att * 100), 1) if total_att > 0 else 0

def _calc_teacher_attendance(teacher_id):
    """Calculate average attendance across all students taught by this teacher."""
    assignments = Assignment.query.filter_by(teacher_id=teacher_id).all()
    class_ids = list(set(a.class_id for a in assignments))
    if not class_ids:
        return 0.0
    students = User.query.filter(User.class_id.in_(class_ids), User.role == 'Student').all()
    if not students:
        return 0.0
    total_att = sum(s.attendance_percentage for s in students if s.attendance_percentage)
    return round(total_att / len(students), 1)
