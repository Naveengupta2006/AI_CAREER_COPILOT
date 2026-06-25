from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from db import Base, engine, SessionLocal
import PyPDF2
try:
    import docx
except ImportError:
    docx = None
import json
import os
import models
from ai import analyze_resume
from scraper import scrape_job_url

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
csrf = CSRFProtect(app)

Base.metadata.create_all(bind=engine)

# ── Home ──────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html", user=session.get("user"))

# ── Signup ────────────────────────────────────────────────────────────────────
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        db = SessionLocal()
        try:
            name     = request.form.get("name")
            email    = request.form.get("email")
            password = request.form.get("password")

            existing = db.query(models.User).filter_by(email=email).first()
            if existing:
                return "User already exists. Please log in."

            new_user = models.User(
                name=name,
                email=email,
                password=generate_password_hash(password)
            )
            db.add(new_user)
            db.commit()
            return redirect("/login")
        finally:
            db.close()

    return render_template("signup.html")

# ── Login ─────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = SessionLocal()
        try:
            email    = request.form.get("email")
            password = request.form.get("password")

            found_user = db.query(models.User).filter_by(email=email).first()
            if found_user and check_password_hash(found_user.password, password):
                session["user"] = found_user.email
                return redirect("/dashboard")
            else:
                return "Invalid credentials. Please try again."
        finally:
            db.close()

    return render_template("login.html")

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    analysis = None

    if request.method == "POST":
        user_goal       = request.form.get("role")
        resume_text     = request.form.get("resume_text")
        job_description = request.form.get("job_description")
        job_url         = request.form.get("job_url")
        file            = request.files.get("file")

        # If a URL was given and no JD was pasted manually, scrape it
        if job_url and not job_description:
            scrape_result = scrape_job_url(job_url)
            if scrape_result["error"]:
                analysis = {"error": f"Job URL error: {scrape_result['error']}"}
            else:
                job_description = scrape_result["text"]

        # File overrides pasted text
        if file and file.filename != "":
            if file.filename.endswith(".pdf"):
                try:
                    pdf_reader = PyPDF2.PdfReader(file)
                    resume_text = "".join(
                        page.extract_text() or "" for page in pdf_reader.pages
                    )
                except Exception as e:
                    analysis = {"error": f"PDF error: {str(e)}"}

            elif file.filename.endswith(".docx"):
                if docx is None:
                    analysis = {"error": "DOCX support not installed. Upload a PDF instead."}
                else:
                    try:
                        doc = docx.Document(file)
                        resume_text = "\n".join(p.text for p in doc.paragraphs)
                    except Exception as e:
                        analysis = {"error": f"DOCX error: {str(e)}"}
            else:
                analysis = {"error": "Unsupported file format. Upload PDF or DOCX."}

        # Only analyze if no file error occurred
        if analysis is None and resume_text and user_goal:
            try:
                analysis = analyze_resume(resume_text, user_goal, job_description)

                db = SessionLocal()
                try:
                    found_user = db.query(models.User).filter_by(email=session["user"]).first()
                    if found_user:
                        report = models.Reports(
                            user_id=found_user.id,
                            goal=user_goal,
                            resume_text=resume_text,
                            analysis_result=json.dumps(analysis)
                        )
                        db.add(report)
                        db.commit()
                finally:
                    db.close()

            except Exception as e:
                analysis = {"error": f"Analysis error: {str(e)}"}

    # Fetch Mock Interview session statistics for analytics dashboard
    db = SessionLocal()
    interview_data = []
    total_sessions = 0
    average_score = 0
    latest_score = 0
    try:
        found_user = db.query(models.User).filter_by(email=session["user"]).first()
        if found_user:
            reports_db = db.query(models.InterviewSessionReport).filter_by(user_id=found_user.id).order_by(models.InterviewSessionReport.created_at.asc()).all()
            total_sessions = len(reports_db)
            if total_sessions > 0:
                average_score = round(sum(r.overall_score for r in reports_db) / total_sessions)
                latest_score = reports_db[-1].overall_score
                for r in reports_db:
                    interview_data.append({
                        "date": r.created_at.strftime("%b %d, %Y"),
                        "score": r.overall_score,
                        "role": r.target_role
                    })
    except Exception as e:
        app.logger.error(f"Error loading dashboard analytics: {e}")
    finally:
        db.close()

    return render_template(
        "dashboard.html",
        analysis=analysis,
        user=session["user"],
        interview_data=interview_data,
        total_sessions=total_sessions,
        average_score=average_score,
        latest_score=latest_score
    )

# ── History ───────────────────────────────────────────────────────────────────
@app.route("/history")
def history():
    if "user" not in session:
        return redirect("/login")

    db = SessionLocal()
    try:
        found_user = db.query(models.User).filter_by(email=session["user"]).first()
        reports    = db.query(models.Reports).filter_by(user_id=found_user.id).all()

        passed_reports = []
        for report in reports:
            try:
                parsed = json.loads(report.analysis_result)
            except Exception:
                parsed = {}
            passed_reports.append({
                "resume_text": report.resume_text,
                "analysis":    parsed
            })

        # Fetch mock interview session reports
        interview_reports_db = db.query(models.InterviewSessionReport).filter_by(user_id=found_user.id).all()
        interview_reports = []
        for ir in interview_reports_db:
            try:
                action_plan_parsed = json.loads(ir.action_plan)
            except Exception:
                action_plan_parsed = []
            interview_reports.append({
                "session_id": ir.session_id,
                "target_role": ir.target_role,
                "overall_score": ir.overall_score,
                "summary": ir.summary,
                "action_plan": action_plan_parsed,
                "created_at": ir.created_at.strftime("%Y-%m-%d %H:%M")
            })
    finally:
        db.close()

    return render_template("history.html", reports=passed_reports, interview_reports=interview_reports)

# ── Voice Interview ───────────────────────────────────────────────────────────
@app.route("/interview", methods=["GET", "POST"])
def interview():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        import uuid
        session["interview_session_id"] = str(uuid.uuid4())
        
        target_role = request.form.get("role") or "Software Engineer"
        file = request.files.get("file")
        
        resume_text = ""
        error = None
        
        if file and file.filename != "":
            if file.filename.endswith(".pdf"):
                try:
                    pdf_reader = PyPDF2.PdfReader(file)
                    resume_text = "".join(
                        page.extract_text() or "" for page in pdf_reader.pages
                    )
                except Exception as e:
                    error = f"PDF read error: {str(e)}"
            else:
                error = "Unsupported file format. Please upload a PDF."
        else:
            error = "Please upload a resume PDF to start."
            
        if not error and resume_text:
            from ai import generate_tailored_questions
            questions = generate_tailored_questions(resume_text, target_role)
            session["interview_questions"] = questions
            session["interview_target_role"] = target_role
            return redirect("/interview")
        else:
            return render_template("interview_start.html", error=error, user=session["user"])

    if "interview_questions" in session:
        return render_template(
            "interview.html",
            user=session["user"],
            target_role=session.get("interview_target_role", "Software Engineer"),
            questions=session["interview_questions"],
            session_id=session.get("interview_session_id")
        )

    return render_template("interview_start.html", user=session["user"])


@app.route("/interview/reset")
def reset_interview_session():
    session.pop("interview_questions", None)
    session.pop("interview_target_role", None)
    session.pop("interview_session_id", None)
    return redirect("/interview")


@app.route("/api/transcribe", methods=["POST"])
@csrf.exempt
def transcribe():
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    if "file" not in request.files:
        return {"error": "No file uploaded"}, 400

    audio_file = request.files["file"]
    
    # Save the file temporarily
    temp_dir = os.path.join(app.root_path, "static", "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"recording_{session['user'].replace('@','_')}.wav")
    audio_file.save(temp_path)
    
    transcription = ""
    error = None
    
    whisper_api_key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("WHISPER_API_KEY", "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")
    
    # 1. Attempt standard NVIDIA Whisper cloud-hosted API
    try:
        from openai import OpenAI
        client_whisper = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=whisper_api_key
        )
        with open(temp_path, "rb") as f:
            resp = client_whisper.audio.transcriptions.create(
                model="openai/whisper-large-v3",
                file=f
            )
        transcription = resp.text
    except Exception as api_err:
        # Fallback to local SpeechRecognition library using Google speech engine
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(temp_path) as source:
                audio_data = recognizer.record(source)
            transcription = recognizer.recognize_google(audio_data)
        except Exception as fallback_err:
            error = f"NVIDIA Whisper API Error: {str(api_err)} | Local Fallback ASR Error: {str(fallback_err)}"
            
    # Clean up the temp file
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception:
        pass
        
    if error and not transcription:
        return {"error": f"Transcription failed: {error}"}, 500
        
    return {"text": transcription}


@app.route("/api/interview/evaluate", methods=["POST"])
@csrf.exempt
def evaluate_answer():
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    data = request.get_json() or {}
    question = data.get("question")
    answer = data.get("answer")
    target_role = data.get("target_role", "Software Engineer")

    if not question or not answer:
        return {"error": "Question and answer are required."}, 400

    from ai import evaluate_interview_answer
    result = evaluate_interview_answer(question, answer, target_role)
    
    # Store evaluation result in PostgreSQL
    db = SessionLocal()
    try:
        found_user = db.query(models.User).filter_by(email=session["user"]).first()
        if found_user:
            session_id = session.get("interview_session_id", "default-session")
            evaluation = models.InterviewEvaluation(
                user_id=found_user.id,
                session_id=session_id,
                question=question,
                answer=answer,
                evaluation_result=json.dumps(result)
            )
            db.add(evaluation)
            db.commit()
    except Exception as e:
        db.rollback()
        app.logger.error(f"PostgreSQL save error: {e}")
    finally:
        db.close()

    return result


@app.route("/interview/report/<session_id>")
def interview_report(session_id):
    if "user" not in session:
        return redirect("/login")

    import datetime
    db = SessionLocal()
    try:
        found_user = db.query(models.User).filter_by(email=session["user"]).first()
        if not found_user:
            return redirect("/login")

        # 1. Check if report already exists in DB
        existing_report = db.query(models.InterviewSessionReport).filter_by(session_id=session_id).first()
        
        # 2. Get all individual evaluations
        evaluations_db = db.query(models.InterviewEvaluation).filter_by(user_id=found_user.id, session_id=session_id).all()
        
        # Parse individual evaluations
        evaluations = []
        for ev in evaluations_db:
            try:
                parsed_res = json.loads(ev.evaluation_result)
            except Exception:
                parsed_res = {}
            evaluations.append({
                "question": ev.question,
                "answer": ev.answer,
                "score": parsed_res.get("score", 0),
                "strong_points": parsed_res.get("strong_points", []),
                "improvements": parsed_res.get("improvements", []),
                "sample_answer": parsed_res.get("sample_answer", "")
            })

        if existing_report:
            try:
                action_plan_parsed = json.loads(existing_report.action_plan)
            except Exception:
                action_plan_parsed = []
            
            report_data = {
                "session_id": existing_report.session_id,
                "target_role": existing_report.target_role,
                "overall_score": existing_report.overall_score,
                "summary": existing_report.summary,
                "action_plan": action_plan_parsed,
                "created_at": existing_report.created_at
            }
        else:
            # Generate new report
            if not evaluations:
                # No evaluations found, don't query AI, just create a mock empty report
                report_data = {
                    "session_id": session_id,
                    "target_role": session.get("interview_target_role", "Software Engineer"),
                    "overall_score": 0,
                    "summary": "No answers were submitted or evaluated in this session. Start a new session to record and submit answers.",
                    "action_plan": [],
                    "created_at": datetime.datetime.utcnow()
                }
            else:
                target_role = session.get("interview_target_role", "Software Engineer")
                
                # Compute average score
                overall_score = round(sum(ev["score"] for ev in evaluations) / len(evaluations))
                
                # Call GPT-5
                from ai import generate_session_feedback_report
                feedback = generate_session_feedback_report(evaluations, target_role)
                
                summary = feedback.get("summary", "")
                action_plan_list = feedback.get("action_plan", [])
                
                new_report = models.InterviewSessionReport(
                    user_id=found_user.id,
                    session_id=session_id,
                    target_role=target_role,
                    overall_score=overall_score,
                    summary=summary,
                    action_plan=json.dumps(action_plan_list)
                )
                db.add(new_report)
                db.commit()
                
                report_data = {
                    "session_id": session_id,
                    "target_role": target_role,
                    "overall_score": overall_score,
                    "summary": summary,
                    "action_plan": action_plan_list,
                    "created_at": datetime.datetime.utcnow()
                }
    except Exception as e:
        db.rollback()
        app.logger.error(f"Error in interview_report: {e}")
        report_data = {
            "session_id": session_id,
            "target_role": session.get("interview_target_role", "Software Engineer"),
            "overall_score": 0,
            "summary": f"System error generating feedback: {str(e)}",
            "action_plan": [],
            "created_at": datetime.datetime.utcnow()
        }
    finally:
        db.close()

    return render_template(
        "interview_report.html",
        user=session["user"],
        report=report_data,
        evaluations=evaluations
    )


# ── Logout ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)