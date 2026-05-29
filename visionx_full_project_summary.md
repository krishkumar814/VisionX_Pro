# VisionX Pro: Comprehensive Technical Project Summary

This document provides an exhaustive architectural and technical audit of the current state of the VisionX Pro workspace. It details the implemented routing, data models, AI integrations, and UI/UX state, while explicitly documenting requested features that are currently missing from the codebase.

## 1. Full Workspace Audit: Codebase Structure

The application is structured as a monolithic Flask application with Blueprints separating the hierarchical workflows:

### Routes (`routes/`)
- **`auth.py`**: Handles User Registration, Login, Logout, and hierarchical redirection (routing authenticated users to their respective role dashboards).
- **`student.py`**: Core student-facing logic containing the Student Dashboard, Test taking & automated grading (`take_test`, `submit_test`), Leaderboard generation (`quiz_leaderboard`), the AI Roadmap generation engine (`learn_new_dashboard`, `generate_roadmap`), and the `chat_with_ai` RAG endpoint.
- **`teacher.py`**: Contains Teacher Dashboard, PDF Material Upload logic (`upload_material`), AI quiz generation for weak topics (`start_test`), and test deactivation logic (`stop_test`).
- **`hod_director.py`**: Contains HOD/Director dashboards, Complaint resolution and escalation logic, and basic AI test generation (`generate_weekly_test`).

### Utility Modules
- **`models.py`**: Master SQLAlchemy Object-Relational Mapper (ORM) schema containing 11 distinct entities.
- **`ai_engine/chat_service.py`**: Contains the `SubjectAgent` for handling Dual-Agent RAG integration using Google Gemini 1.5 Flash.

---

## 2. Database Deep-Dive & Target Logic Audit

### 2.1 RedeemableCredits & Vouchers (The fee discount economy)
**STATUS: NOT IMPLEMENTED**
Currently, the database only models an integer column `credits = db.Column(db.Integer, default=0)` inside the `User` model. There are **no associated tables or logic** for `RedeemableCredits`, discount economy, or `Vouchers`. The platform tracks student scores securely (via `QuizAttempt`), but the actual redemption marketplace code does not currently exist in the repository.

### 2.2 Complaint (Token-based anonymity and 15-day escalation)
**STATUS: IMPLEMENTED**
- **Model**: Uses the `Complaint` table.
- **Anonymity**: Instead of linking a foreign key to a `User`, it utilizes a universally unique `secret_token = db.Column(db.String(50), unique=True, nullable=False)` preventing the platform from associating complaints with specific students.
- **Escalation Logic**: Located in `routes/hod_director.py` under the `/hod/dashboard` endpoint. Every time the dashboard is loaded, it triggers an auto-verification loop iterating through `Pending` complaints. If `(datetime.utcnow() - c.created_at).days > 15`, it securely mutates `c.status = 'Escalated'` and `c.assigned_to = 'Director'`.

### 2.3 WeakTopic (Mapping Teacher-assigned vs AI-detected topics)
**STATUS: PARTIALLY IMPLEMENTED (No Mapping Model)**
- There is no independent `WeakTopic` database model schema.
- **Current Logic**: Weak Topics are recorded simply as a string column inside `TestSession`: `quiz_type="Weak Topic"` and `topics=db.Column(...)`. 
- **AI Implementation**: Found in `routes/teacher.py` (`generate_ai_questions`). If the `progressive=True` flag is triggered, the prompt inherently restricts the Gemini model to start tests from an "Easy" difficulty specifically on the provided `topics` boundary and escalate to "Hard". It lacks an autonomous AI-detection mechanism for isolating these topics from student historical failure data.

### 2.4 LearningPath & Section (Section-gating and YT/GFG link storage)
**STATUS: IMPLEMENTED (Dynamic Logic)**
- **Models**: `Roadmap` (stores JSON string of sections via `db.Column(db.JSON)`) and `StudentProgress` (stores gating point via `current_section = db.Column(db.Integer)`).
- **Section-Gating Logic**: Located in `student.py` -> `roadmap_view`. A student can only trigger evaluations or see elements belonging to sections less than or equal to their integer recorded in `StudentProgress.current_section`. Successfully passing the section quiz increments this integer.
- **YT/GFG Links**: Dynamic UI implementation. Rather than storing brittle hardcoded URLs, the `templates/roadmap_view.html` securely injects the `roadmap.tech_name` and the AI-generated `topic` into unified query parameters:
  - `https://www.youtube.com/results?search_query={{topic}}+{{tech_name}}+tutorial`
  - `https://www.google.com/search?q={{topic}}+{{tech_name}}+geeks+for+geeks`

---

## 3. AI & RAG Logic Extraction

### 3.1 Targeted RAG code & Context Isolation
**STATUS: IMPLEMENTED**
The system actively blocks cross-document hallucinations by implementing a physical `material_id` selector in the chat UI.
When invoked in `/student/chat`:
1. **Document Loading**: PyMuPDF (`fitz`) connects exclusively to the isolated `file_path` of the explicitly declared `material_id`. It extracts specifically pages 1-10 to respect the prompt context window and blocks memory bleeding from other PDFs.
2. **Dual-Agent Architecture** (`chat_service.py`):
    - **Step 1 (Extraction Agent)**: Given the raw, isolated document text, Agent 1 is explicitly prompted to perform Retrieval by extracting ONLY exact facts pertaining to the specific user question. It prevents LLM generic-memory hallucinations. If blocked/failed, safety wrappers default to `NOT_FOUND`.
    - **Step 2 (Simplifying Agent)**: A secondary AI context is initialized strictly on the cleaned text block from Agent 1, discarding jargon and outputting clear, student-level instructional formatting. 

### 3.2 HOD Mega-Test Generator (Distribution Parsing)
**STATUS: NOT IMPLEMENTED**
The current HOD logic only utilizes a simplistic, standardized API wrapper located in `routes/hod_director.py` (`generate_weekly_test`). The system prompts Gemini to format `5 MCQs` on a *single* manually declared `request.form.get('topic')`. There is zero architecture present to systematically distribute topics globally (e.g. 3 questions X, 2 for Y) or consolidate metrics to build dynamic Mega-Tests. 

### 3.3 Teacher Support Module (Slides / Analogies)
**STATUS: NOT IMPLEMENTED**
The codebase completely lacks logic connecting poor student performance tracking with backend pedagogical material delivery for teachers. Current AI logic is restricted to student assessment (Quiz generation) and tutoring (Chat system). 

---

## 4. Feature Status Report: UI & Dashboards
- **Student Dashboard (`student_dashboard.html`)**: Complete. Supports active assignments routing, adaptive AI Roadmap generation panel, and dynamic PDF view navigation.
- **Teacher Dashboard (`teacher_dashboard.html`)**: Operable point. Handles uploading specific structural PDFs to `static/uploads/subject_X`, controls live start/stop triggers for exams, and manages class tracking.
- **HOD Dashboard (`hod_dashboard.html`)**: Complete. Contains a grid viewing active Weekly Test sessions. UI manages Complaint resolutions natively, including automatic or manual triggering of `Escalate to Director` features.
- **Director Dashboard (`director.dashboard`)**: Complete. Solely focuses on escalated administrative tasks and Final Resolution mechanisms for highly delayed complaints. 
- **Hall of Fame Banner (`leaderboard.html`)**: Functional. A dedicated UI that globally ranks the student class schema logically sorted by their cumulative SQL integer ranking in the `User.credits` token system.
