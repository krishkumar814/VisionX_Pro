# VisionX Pro & Sentry-AI: Project Blueprint

## Project Goal
A multi-agent AI system for educational quiz management (VisionX Pro) and autonomous road safety (Sentry-AI).

## Core Logic Implemented
1. **Teacher-Led Sessions**: Uses `TestSession` model. Only 1 active session per class/subject.
2. **AI Question Factory**: Gemini 1.5 Flash generates MCQs based on specific topics provided by the Teacher.
3. **Smart Grader**: Student submissions are cleaned (strip whitespace, lowercase, remove "A:" prefixes) before comparing to the `correct_answer` in the DB.
4. **One-Time Access**: `QuizAttempt` table prevents students from retaking the same test session.

## Database Schema (Current)
- `User`: Standard auth + `credits` + `role` (Technical Head, Teacher, Student).
- `Subject`: Course names.
- `QuestionBank`: Stores `question_text`, `options` (comma-separated), and `correct_answer` (Full Text).
- `TestSession`: `is_active` toggle + `topics` string.
- `QuizAttempt`: Logs student ID, session ID, and score.

## Next High-Priority Tasks
1. Build **Teacher Dashboard UI** (Start/Stop test form).
2. Build **Student Leaderboard** (Rank by total credits).
3. Develop **Mid-Term Report** documentation.