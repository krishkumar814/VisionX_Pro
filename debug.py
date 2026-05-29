from app import app
from models import db, Complaint, User, Roadmap
import json

with app.app_context():
    # Fix old complaints by assigning them to a default student
    student = User.query.filter_by(role='Student').first()
    if student:
        complaints = Complaint.query.filter_by(student_id=None).all()
        for c in complaints:
            c.student_id = student.id
            print(f"Assigned complaint {c.secret_token} to student {student.username}")
        db.session.commit()
    else:
        print("No student found!")

    # Check roadmaps
    roadmaps = Roadmap.query.all()
    for r in roadmaps:
        print(f"Roadmap ID: {r.id}, Tech: {r.tech_name}")
