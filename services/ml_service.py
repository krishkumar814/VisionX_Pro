import os
import joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from models import db, User, QuizAttempt, TestSession

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ml_models')
MODEL_PATH = os.path.join(MODEL_DIR, 'performance_model.joblib')

def extract_features(student_id):
    student = db.session.get(User, student_id)
    if not student:
        return [0, 0, 0] # fallback defaults

    attendance = student.attendance_percentage or 0.0
    credits = student.credits or 0

    # Calculate average Weekly Quiz and Weak Topic scores
    attempts = QuizAttempt.query.filter_by(student_id=student_id).all()
    weekly_scores = []
    weak_topic_scores = []

    for attempt in attempts:
        session = db.session.get(TestSession, attempt.session_id)
        if session:
            # We assume out of 5 for simplicity since take_test fetches 5 questions, 
            # or we calculate percentage if we knew total. Just use raw score.
            if session.quiz_type == 'Weekly':
                weekly_scores.append(attempt.score)
            elif session.quiz_type == 'Weak Topic':
                weak_topic_scores.append(attempt.score)

    avg_weekly = sum(weekly_scores) / len(weekly_scores) if weekly_scores else 0
    avg_weak = sum(weak_topic_scores) / len(weak_topic_scores) if weak_topic_scores else 0

    return [attendance, credits, (avg_weekly + avg_weak) / 2.0]

def determine_actual_label(attendance, credits, avg_score):
    """
    A simple heuristic for bootstrapping labels based on current data.
    Categories: 'Needs Improvement', 'Average', 'Good', 'Excellent'
    """
    score = (attendance * 0.4) + (min(credits, 1000) / 1000.0 * 100 * 0.2) + (avg_score / 5.0 * 100 * 0.4)
    if score >= 80:
        return 'Excellent'
    elif score >= 60:
        return 'Good'
    elif score >= 40:
        return 'Average'
    else:
        return 'Needs Improvement'

def train_performance_model():
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)

    students = User.query.filter_by(role='Student').all()
    
    X = []
    y = []

    # Real data
    for st in students:
        feats = extract_features(st.id)
        X.append(feats)
        y.append(determine_actual_label(*feats))

    # We need to bootstrap with synthetic data to ensure there's enough samples 
    # to train the Model if the DB is empty or very small.
    if len(X) < 20:
        np.random.seed(42)
        for _ in range(50):
            syn_att = np.random.uniform(0, 100)
            syn_cred = np.random.uniform(0, 1000)
            syn_score = np.random.uniform(0, 5)
            feats = [syn_att, syn_cred, syn_score]
            X.append(feats)
            y.append(determine_actual_label(*feats))

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X, y)

    joblib.dump(clf, MODEL_PATH)
    print(f"Model successfully saved to {MODEL_PATH} with {len(X)} training samples.")

def predict_student_performance(student_id):
    if not os.path.exists(MODEL_PATH):
        return "Model Not Trained"

    clf = joblib.load(MODEL_PATH)
    feats = extract_features(student_id)
    
    # Predict takes 2D array
    prediction = clf.predict([feats])
    return prediction[0]

def get_recommendations(prediction, weak_topics=None):
    if weak_topics is None:
        weak_topics = []

    recs = []
    
    # 1. Base ML recommendations
    if prediction == 'Needs Improvement':
        recs.append({
            'text': 'Focus on taking more Quizzes to improve your foundation.',
            'action': 'Take Quiz',
            'reason': 'Your overall performance prediction suggests needing stronger fundamentals.'
        })
        recs.append({
            'text': 'Review Study Material carefully before attempting new quizzes.',
            'action': 'Read PDF',
            'reason': 'Your overall performance prediction suggests needing stronger fundamentals.'
        })
    elif prediction == 'Average':
        recs.append({
            'text': 'Practice with more Quizzes to solidify your understanding.',
            'action': 'Take Quiz',
            'reason': 'Consistent practice will raise your average scores.'
        })
    elif prediction in ['Good', 'Excellent']:
        recs.append({
            'text': 'Great job! Explore Advanced Topics in the Learn New module.',
            'action': 'Learn New',
            'reason': 'You have strong performance and are ready for advanced material.'
        })
        recs.append({
            'text': 'Challenge yourself with harder quizzes.',
            'action': 'Take Quiz',
            'reason': 'You are ready to test your knowledge with harder difficulty.'
        })
    else:
        recs.append({
            'text': 'Keep exploring the platform and taking quizzes!',
            'action': 'Explore',
            'reason': 'Consistent learning is key.'
        })

    # 2. Dynamic recommendations based on weak topics
    for wt in weak_topics:
        topic_name = wt['topic']
        subject_name = wt['subject']
        recs.append({
            'text': f'CRITICAL: Review the AI Roadmap for "{topic_name}" ({subject_name})',
            'action': 'Learn New',
            'reason': f'You are weak in {topic_name} (score < 50%), so this is recommended.'
        })
        recs.append({
            'text': f'Ask the Chatbot to explain "{topic_name}" in simpler terms.',
            'action': 'Ask Chatbot',
            'reason': f'You are weak in {topic_name} (score < 50%), so this is recommended.'
        })

    return recs
