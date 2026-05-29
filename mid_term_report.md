# VisionX Pro & Sentry-AI: Mid-Term Report

## 1. Project Overview
**VisionX Pro** is an innovative multi-agent AI framework developed for educational quiz management, coupled with **Sentry-AI** for real-time intelligent monitoring. The platform bridges the gap between structured curriculum and adaptive AI assessment, allowing educators to instantly generate high-quality quizzes tailored to specific topics and difficulty levels.

## 2. Core Architecture
The system relies on a seamless Flask monolith integrating with SQLite (SQLAlchemy) and the Gemini API for generative tasks.

### 2.1 Technologies Used
- **Backend**: Flask (Python)
- **Database**: SQLite with Flask-SQLAlchemy
- **Authentication**: Flask-Login and Flask-Bcrypt
- **AI Integration**: Google Generative AI (`gemini-2.5-flash`)
- **Frontend**: Bootstrap 5 + Vanilla JS
- **Version Control**: Git & GitHub

## 3. Database Schema
Organized efficiently to allow rapid queries for roles, class assignments, and quiz sessions:

- `User`: Handles RBAC (Technical Head, Teacher, Student, HOD). Includes student `credits`.
- `Class` & `Subject`: Relational links representing the academic structure.
- `Assignment`: Resolution table linking a `Teacher` to specific `Subject`s and `Class`es.
- `StudyMaterial`: Repositories of PDF uploads for future RAG index.
- `TestSession`: Configures AI-generated tests per class/subject with an operational toggle (`is_active`).
- `QuestionBank`: Houses the generative MCQs created by the AI Engine.
- `QuizAttempt`: A one-time access log documenting student submissions to enforce test integrity.

## 4. Key Features Implemented

### 4.1 AI Question Factory (Teacher-Led)
Teachers can effortlessly spawn dynamic multiple-choice question sets by providing topics. 
The **AI Question Factory** triggers the Gemini `2.5-flash` model via an optimized prompt to curate standard 4-option MCQs.

### 4.2 Automated Smart Grading
Upon submission, the robust Smart Grader validates user inputs by stripping whitespace and neutralizing casing, preventing superficial failures on otherwise correct answers. Valid hits yield +20 Credits for the student.

### 4.3 Student Gamification (Leaderboard)
Engagement is preserved via gamification. Students earn "Credits" for successful Quiz attempts, visible on the globally accessible **Student Leaderboard** showcasing their mastery progression relative to their peers.

## 5. Future Roadmap
1. **Intelligent Material Parsing (RAG)**: Connect the `StudyMaterial` PDF uploads to the `SubjectAgent` using semantic search (ChromaDB or FAISS) for pinpoint QA chatbot functionality.
2. **Multi-Agent Question Validation**: Implement an automated second-pass via another Gemini logic route to determine the difficulty and strict validity (no-hallucination) of the Question.
3. **Sentry-AI Expansion**: Integrate computer vision analysis pipelines for Sentry's automated environment scanning module.
