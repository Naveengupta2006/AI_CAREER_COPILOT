from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from db import Base, engine, SessionLocal, run_migrations
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
run_migrations()  # Safely add new columns to existing tables

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
            return render_template("interview_start.html", error=error, user=session["user"], title="Voice Interview Prep Lab")

    if "interview_questions" in session:
        return render_template(
            "interview.html",
            user=session["user"],
            target_role=session.get("interview_target_role", "Software Engineer"),
            questions=session["interview_questions"],
            session_id=session.get("interview_session_id")
        )

    return render_template("interview_start.html", user=session["user"], title="Voice Interview Prep Lab")


@app.route("/interview/reset")
def reset_interview_session():
    session.pop("interview_questions", None)
    session.pop("interview_target_role", None)
    session.pop("interview_session_id", None)
    return redirect("/interview")

# ── Virtual Interview ───────────────────────────────────────────────────────────
@app.route("/virtual_interview", methods=["GET", "POST"])
def virtual_interview():
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
            session["virtual_interview_questions"] = questions
            session["virtual_interview_target_role"] = target_role
            return redirect("/virtual_interview")
        else:
            return render_template("interview_start.html", error=error, user=session["user"], title="AI Virtual Interview Room")

    if "virtual_interview_questions" in session:
        return render_template(
            "virtual_interview.html",
            user=session["user"],
            target_role=session.get("virtual_interview_target_role", "Software Engineer"),
            questions=session["virtual_interview_questions"],
            session_id=session.get("interview_session_id")
        )

    return render_template("interview_start.html", user=session["user"], title="AI Virtual Interview Room")


@app.route("/virtual_interview/reset")
def reset_virtual_interview_session():
    session.pop("virtual_interview_questions", None)
    session.pop("virtual_interview_target_role", None)
    session.pop("interview_session_id", None)
    return redirect("/virtual_interview")


# ── Phase 3: AI Interview Room (UI pages) ────────────────────────────────────
@app.route("/interview/v2")
def interview_v2_start():
    if "user" not in session:
        return redirect("/login")
    return render_template("interview_v2_start.html", user=session["user"])

@app.route("/interview/v2/room")
def interview_v2_room():
    if "user" not in session:
        return redirect("/login")
    return render_template("interview_v2.html", user=session["user"])



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
    temp_path = os.path.join(temp_dir, f"recording_{session['user'].replace('@','_')}.webm")
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
    
    # Calculate Readiness Score
    c_score = result.get("communication_score", 0)
    t_score = result.get("technical_score", 0)
    conf_score = result.get("confidence_score", 0)
    p_score = result.get("problem_solving_score", 0)
    readiness_score = round((c_score + t_score + conf_score + p_score) / 4)
    result["score"] = readiness_score
    
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
                "communication_score": parsed_res.get("communication_score", 0),
                "technical_score": parsed_res.get("technical_score", 0),
                "confidence_score": parsed_res.get("confidence_score", 0),
                "problem_solving_score": parsed_res.get("problem_solving_score", 0),
                "strong_points": parsed_res.get("strong_points", []),
                "improvements": parsed_res.get("improvements", []),
                "sample_answer": parsed_res.get("sample_answer", "")
            })

        # Calculate session averages
        avg_comm = round(sum(ev.get("communication_score", 0) for ev in evaluations) / len(evaluations)) if evaluations else 0
        avg_tech = round(sum(ev.get("technical_score", 0) for ev in evaluations) / len(evaluations)) if evaluations else 0
        avg_conf = round(sum(ev.get("confidence_score", 0) for ev in evaluations) / len(evaluations)) if evaluations else 0
        avg_prob = round(sum(ev.get("problem_solving_score", 0) for ev in evaluations) / len(evaluations)) if evaluations else 0

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
                "created_at": existing_report.created_at,
                "avg_comm": avg_comm,
                "avg_tech": avg_tech,
                "avg_conf": avg_conf,
                "avg_prob": avg_prob
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
                    "created_at": datetime.datetime.utcnow(),
                    "avg_comm": 0,
                    "avg_tech": 0,
                    "avg_conf": 0,
                    "avg_prob": 0
                }
            else:
                target_role = session.get("interview_target_role", "Software Engineer")
                
                # Compute average score
                overall_score = round(sum(ev["score"] for ev in evaluations) / len(evaluations))
                
                # Call GPT-5
                from ai import generate_session_feedback_report
                feedback = generate_session_feedback_report(evaluations, target_role)
                
                summary = feedback.get("summary", "")
                action_data = {
                    "top_strengths": feedback.get("top_strengths", []),
                    "top_weaknesses": feedback.get("top_weaknesses", [])
                }
                
                new_report = models.InterviewSessionReport(
                    user_id=found_user.id,
                    session_id=session_id,
                    target_role=target_role,
                    overall_score=overall_score,
                    summary=summary,
                    action_plan=json.dumps(action_data),
                    avg_comm=avg_comm,
                    avg_tech=avg_tech,
                    avg_conf=avg_conf,
                    avg_prob=avg_prob
                )
                db.add(new_report)
                db.commit()
                
                report_data = {
                    "session_id": session_id,
                    "target_role": target_role,
                    "overall_score": overall_score,
                    "summary": summary,
                    "action_plan": action_data,
                    "created_at": datetime.datetime.utcnow(),
                    "avg_comm": avg_comm,
                    "avg_tech": avg_tech,
                    "avg_conf": avg_conf,
                    "avg_prob": avg_prob
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
            "created_at": datetime.datetime.utcnow(),
            "avg_comm": 0,
            "avg_tech": 0,
            "avg_conf": 0,
            "avg_prob": 0
        }
    finally:
        db.close()

    return render_template(
        "interview_report.html",
        user=session["user"],
        report=report_data,
        evaluations=evaluations
    )



# ══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Interview Pipeline API (5 routes)
# ══════════════════════════════════════════════════════════════════════════════

import base64

# ── POST /api/v2/interview/start ──────────────────────────────────────────────
@app.route("/api/v2/interview/start", methods=["POST"])
@csrf.exempt
def v2_interview_start():
    """
    Body (JSON or multipart):
      role        : str  — target role
      resume_text : str  — raw resume text (optional if file uploaded)
      file        : PDF  — resume file (optional)

    Creates an InterviewSession row, generates Q1, optionally speaks it via TTS.
    Returns:
      { session_id, question_text, question_type, audio_b64 (may be null) }
    """
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    # ── Parse request body (JSON or multipart) ──────────────────
    if request.is_json:
        data        = request.get_json() or {}
        role        = data.get("role", "Software Engineer")
        resume_text = data.get("resume_text", "")
        file        = None
    else:
        role        = request.form.get("role", "Software Engineer")
        resume_text = request.form.get("resume_text", "")
        file        = request.files.get("file")

    if file and file.filename.endswith(".pdf"):
        try:
            pdf_reader  = PyPDF2.PdfReader(file)
            resume_text = "".join(page.extract_text() or "" for page in pdf_reader.pages)
        except Exception as e:
            return {"error": f"PDF parse error: {e}"}, 400

    db = SessionLocal()
    try:
        found_user = db.query(models.User).filter_by(email=session["user"]).first()
        if not found_user:
            return {"error": "User not found"}, 404

        # Phase 4: candidate name for greeting
        candidate_name = getattr(found_user, "name", None) or session["user"].split("@")[0]

        from ai import plan_interview_questions, generate_greeting, generate_interview_question, text_to_speech

        # ── 1. Generate the typed 10-question plan ───────────────
        plan = plan_interview_questions(role, resume_text or "")

        # ── 2. Generate Q1 from plan[0] ──────────────────────────
        q1_type  = plan[0].get("type", "hr") if plan else "hr"
        q1_topic = plan[0].get("topic_hint", "self introduction") if plan else "self introduction"
        # Re-use existing generator but hint the type in the prompt via asked_questions trick
        q1 = generate_interview_question(
            role, resume_text or "",
            asked_questions=[f"[type:{q1_type} topic:{q1_topic}]"],
            question_number=1
        )
        q1_text = q1.get("question_text", f"Tell me about yourself and why you are interested in the {role} role.")

        # ── 3. Build greeting ─────────────────────────────────────
        greeting = generate_greeting(candidate_name, role)

        # ── 4. Initialise chat history ────────────────────────────
        system_msg = {
            "role": "system",
            "content": (
                f"You are a professional AI interviewer conducting a {role} interview.\n"
                f"Candidate name: {candidate_name}\n"
                f"Interview plan: 2 HR, 5 Technical, 2 Behavioural, 1 Situational questions.\n"
                f"Resume context: {(resume_text or '')[:2000]}\n"
                "Be professional, encouraging, and thorough. Evaluate answers honestly.\n"
                "When asked to evaluate, return ONLY valid JSON."
            )
        }
        opening_msg = {
            "role": "assistant",
            "content": f"{greeting}\n\n{q1_text}"
        }
        chat_history = [system_msg, opening_msg]

        # ── 5. Persist session ────────────────────────────────────
        iv_session = models.InterviewSession(
            user_id=found_user.id,
            role=role,
            resume_text=resume_text or None,
            candidate_name=candidate_name,
            chat_history=json.dumps(chat_history),
            question_plan=json.dumps(plan),
            current_q_idx=0,
        )
        db.add(iv_session)
        db.commit()
        db.refresh(iv_session)
        session_id = iv_session.id

        # ── 6. Create Q1 answer row ───────────────────────────────
        answer_row = models.InterviewAnswer(
            session_id=session_id,
            question_text=q1_text,
            question_type=q1_type,
        )
        db.add(answer_row)
        db.commit()

        # ── 7. TTS: speak greeting + Q1 ──────────────────────────
        tts_text    = f"{greeting} {q1_text}"
        audio_bytes = text_to_speech(tts_text)
        audio_b64   = base64.b64encode(audio_bytes).decode() if audio_bytes else None

        return {
            "session_id":     session_id,
            "answer_id":      answer_row.id,
            "greeting":       greeting,
            "question_text":  q1_text,
            "question_type":  q1_type,
            "question_num":   1,
            "total_planned":  len(plan),
            "audio_b64":      audio_b64,
        }

    except Exception as e:
        db.rollback()
        app.logger.error(f"v2_interview_start error: {e}")
        return {"error": str(e)}, 500
    finally:
        db.close()


# ── POST /api/v2/interview/transcribe ─────────────────────────────────────────
@app.route("/api/v2/interview/transcribe", methods=["POST"])
@csrf.exempt
def v2_interview_transcribe():
    """
    Body (multipart):
      file : audio blob (webm / wav / mp3)

    Runs Whisper and returns the transcript text.
    Returns: { transcript }
    """
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    if "file" not in request.files:
        return {"error": "No audio file provided"}, 400

    audio_file = request.files["file"]
    temp_dir   = os.path.join(app.root_path, "static", "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    safe_name = session["user"].replace("@", "_").replace(".", "_")
    temp_path = os.path.join(temp_dir, f"v2_{safe_name}.webm")
    audio_file.save(temp_path)

    live_transcript = request.form.get("live_transcript", "").strip()
    transcript = ""
    error      = None

    whisper_key = os.environ.get("NVIDIA_API_KEY", "")
    try:
        from openai import OpenAI as _OAI
        wh_client = _OAI(base_url="https://integrate.api.nvidia.com/v1", api_key=whisper_key)
        with open(temp_path, "rb") as f:
            resp = wh_client.audio.transcriptions.create(
                model="openai/whisper-large-v3", file=f
            )
        transcript = resp.text
    except Exception as e1:
        if live_transcript:
            transcript = live_transcript
        else:
            # If both Whisper and live_transcript fail, provide a placeholder text
            # so the interview proceeds and the LLM can handle it gracefully.
            transcript = "[No audio detected or transcription failed]"
            error = None

    try:
        os.remove(temp_path)
    except Exception:
        pass

    if error and not transcript:
        return {"error": error}, 500

    return {"transcript": transcript}


# ── POST /api/v2/interview/evaluate ──────────────────────────────────────────
@app.route("/api/v2/interview/evaluate", methods=["POST"])
@csrf.exempt
def v2_interview_evaluate():
    """
    Body (JSON):
      answer_id   : int  — InterviewAnswer row to update
      answer_text : str  — transcript of the candidate's spoken answer

    GPT evaluates the answer and persists 4 scores + follow-up decision.
    Returns:
      { comm_score, tech_score, conf_score, problem_score, overall_score,
        strengths, weaknesses, follow_up_needed, follow_up_reason }
    """
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    data        = request.get_json() or {}
    answer_id   = data.get("answer_id")
    answer_text = (data.get("answer_text") or "").strip()

    if not answer_id or not answer_text:
        return {"error": "answer_id and answer_text are required"}, 400

    db = SessionLocal()
    try:
        answer_row = db.query(models.InterviewAnswer).filter_by(id=answer_id).first()
        if not answer_row:
            return {"error": "Answer row not found"}, 404

        iv_session = db.query(models.InterviewSession).filter_by(id=answer_row.session_id).first()
        role = iv_session.role if iv_session else "Software Engineer"

        # ── Phase 4: load conversation thread + plan from DB ────
        chat_history  = json.loads(iv_session.chat_history)  if iv_session.chat_history  else []
        question_plan = json.loads(iv_session.question_plan) if iv_session.question_plan else []
        current_q_idx = iv_session.current_q_idx or 0
        is_follow_up  = (answer_row.question_type == "follow_up")

        from ai import interviewer_turn
        result = interviewer_turn(
            chat_history=chat_history,
            question_plan=question_plan,
            current_q_idx=current_q_idx,
            answer_text=answer_text,
            role=role,
            is_follow_up=is_follow_up,
        )

        # ── Persist updated conversation thread ──────────────────
        iv_session.chat_history = json.dumps(result["updated_history"])
        if result.get("advance_idx"):
            iv_session.current_q_idx = current_q_idx + 1

        # ── Persist answer evaluation ─────────────────────────────
        answer_row.answer_text     = answer_text
        answer_row.score           = result.get("overall_score")
        answer_row.strengths       = json.dumps(result.get("strengths", []))
        answer_row.weaknesses      = json.dumps(result.get("weaknesses", []))
        answer_row.follow_up_asked = bool(result.get("follow_up_needed", False))
        
        answer_row.comm_score      = result.get("comm_score")
        answer_row.tech_score      = result.get("tech_score")
        answer_row.conf_score      = result.get("conf_score")
        answer_row.problem_score   = result.get("problem_score")
        db.commit()

        return {
            "answer_id":          answer_id,
            "comm_score":         result.get("comm_score"),
            "tech_score":         result.get("tech_score"),
            "conf_score":         result.get("conf_score"),
            "problem_score":      result.get("problem_score"),
            "overall_score":      result.get("overall_score"),
            "strengths":          result.get("strengths", []),
            "weaknesses":         result.get("weaknesses", []),
            "follow_up_needed":   result.get("follow_up_needed", False),
            "follow_up_reason":   result.get("follow_up_reason", ""),
            # Pre-computed next question — frontend passes this back to /next
            "next_question_text": result.get("next_question", ""),
            "next_question_type": result.get("next_question_type", "technical"),
        }

    except Exception as e:
        db.rollback()
        app.logger.error(f"v2_interview_evaluate error: {e}")
        return {"error": str(e)}, 500
    finally:
        db.close()


# ── POST /api/v2/interview/next ───────────────────────────────────────────────
@app.route("/api/v2/interview/next", methods=["POST"])
@csrf.exempt
def v2_interview_next():
    """
    Body (JSON):
      session_id        : int
      follow_up_needed  : bool  (from /evaluate response)
      follow_up_reason  : str   (from /evaluate response)
      last_answer_id    : int   (the answer_id just evaluated)

    If follow_up_needed → generates a follow-up question for the same answer row.
    Otherwise → generates the next main question and creates a new answer row.
    Returns:
      { answer_id, question_text, question_type, question_num, is_follow_up, audio_b64 }
    """
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    data               = request.get_json() or {}
    session_id         = data.get("session_id")
    follow_up_needed   = data.get("follow_up_needed", False)
    follow_up_reason   = data.get("follow_up_reason", "")
    last_answer_id     = data.get("last_answer_id")
    # Phase 4: pre-computed next question from /evaluate response
    next_question_text = (data.get("next_question_text") or "").strip()
    next_question_type = (data.get("next_question_type") or "technical").strip()

    if not session_id:
        return {"error": "session_id is required"}, 400

    db = SessionLocal()
    try:
        iv_session = db.query(models.InterviewSession).filter_by(id=session_id).first()
        if not iv_session:
            return {"error": "Session not found"}, 404

        from ai import text_to_speech

        if next_question_text:
            # ── Phase 4 fast path: question was pre-generated by /evaluate ──
            # Just create the DB row and return TTS — no extra GPT call needed
            q_text = next_question_text
            q_type = next_question_type if next_question_type else ("follow_up" if follow_up_needed else "technical")
            is_follow_up = follow_up_needed
        else:
            # ── Legacy fallback (Phase 2 behaviour) ───────────────────────
            from ai import generate_interview_question, generate_follow_up_question
            existing        = db.query(models.InterviewAnswer).filter_by(session_id=session_id).all()
            asked_questions = [a.question_text for a in existing]
            question_num    = len(existing) + 1
            role        = iv_session.role
            resume_text = iv_session.resume_text or ""

            if follow_up_needed and last_answer_id:
                last_ans = db.query(models.InterviewAnswer).filter_by(id=last_answer_id).first()
                q = generate_follow_up_question(
                    original_question=last_ans.question_text if last_ans else "",
                    answer_text=last_ans.answer_text or "" if last_ans else "",
                    follow_up_reason=follow_up_reason,
                    role=role,
                )
                is_follow_up = True
            else:
                q = generate_interview_question(role, resume_text, asked_questions, question_num)
                is_follow_up = False
            q_text = q["question_text"]
            q_type = q.get("question_type", "technical")

        # Create a new InterviewAnswer row for the next question
        existing_count = db.query(models.InterviewAnswer).filter_by(session_id=session_id).count()
        new_answer = models.InterviewAnswer(
            session_id=session_id,
            question_text=q_text,
            question_type=q_type,
        )
        db.add(new_answer)
        db.commit()
        db.refresh(new_answer)

        # TTS for the new question only (greeting already spoken at start)
        audio_bytes = text_to_speech(q_text)
        audio_b64   = base64.b64encode(audio_bytes).decode() if audio_bytes else None

        return {
            "answer_id":     new_answer.id,
            "question_text": q_text,
            "question_type": q_type,
            "question_num":  existing_count + 1,
            "is_follow_up":  is_follow_up,
            "audio_b64":     audio_b64,
        }

    except Exception as e:
        db.rollback()
        app.logger.error(f"v2_interview_next error: {e}")
        return {"error": str(e)}, 500
    finally:
        db.close()


# ── POST /api/v2/interview/finish ─────────────────────────────────────────────
@app.route("/api/v2/interview/finish", methods=["POST"])
@csrf.exempt
def v2_interview_finish():
    """
    Body (JSON):
      session_id : int

    Aggregates all evaluated InterviewAnswer rows for the session,
    computes final scores, generates a report via GPT, and saves:
      - InterviewSession (scores + hiring_recommendation)
      - InterviewReport  (strengths_summary, weaknesses_summary, roadmap, suggestion)

    Returns the full report payload.
    """
    if "user" not in session:
        return {"error": "Unauthorized"}, 401

    data       = request.get_json() or {}
    session_id = data.get("session_id")

    if not session_id:
        return {"error": "session_id is required"}, 400

    db = SessionLocal()
    try:
        iv_session = db.query(models.InterviewSession).filter_by(id=session_id).first()
        if not iv_session:
            return {"error": "Session not found"}, 404

        # Collect all answered questions
        answers_db = (
            db.query(models.InterviewAnswer)
            .filter_by(session_id=session_id)
            .filter(models.InterviewAnswer.answer_text.isnot(None))
            .all()
        )

        session_answers = []
        for a in answers_db:
            session_answers.append({
                "question_text": a.question_text,
                "question_type": a.question_type,
                "answer_text":   a.answer_text,
                "comm_score":    a.comm_score,
                "tech_score":    a.tech_score,
                "conf_score":    a.conf_score,
                "problem_score": a.problem_score,
                "overall_score": a.score,       # 0-10
                "strengths":     json.loads(a.strengths)   if a.strengths  else [],
                "weaknesses":    json.loads(a.weaknesses)  if a.weaknesses else [],
            })

        from ai import generate_final_report_phase2
        report = generate_final_report_phase2(session_answers, iv_session.role)

        # Persist aggregated scores to InterviewSession
        iv_session.overall_score         = report["overall_score"]
        iv_session.comm_score            = report["comm_score"]
        iv_session.tech_score            = report["tech_score"]
        iv_session.conf_score            = report["conf_score"]
        iv_session.problem_score         = report["problem_score"]
        iv_session.hiring_recommendation = report["hiring_recommendation"]

        # Create or update InterviewReport
        existing_report = db.query(models.InterviewReport).filter_by(session_id=session_id).first()
        if existing_report:
            existing_report.strengths_summary  = report["strengths_summary"]
            existing_report.weaknesses_summary = report["weaknesses_summary"]
            existing_report.roadmap            = json.dumps(report["roadmap"])
            existing_report.suggestion         = report["suggestion"]
            existing_report.suggested_answers  = json.dumps(report.get("suggested_answers", []))
        else:
            new_report = models.InterviewReport(
                session_id=session_id,
                strengths_summary=report["strengths_summary"],
                weaknesses_summary=report["weaknesses_summary"],
                roadmap=json.dumps(report["roadmap"]),
                suggestion=report["suggestion"],
                suggested_answers=json.dumps(report.get("suggested_answers", [])),
            )
            db.add(new_report)

        db.commit()

        return {
            "session_id":            session_id,
            "role":                  iv_session.role,
            "overall_score":         report["overall_score"],
            "comm_score":            report["comm_score"],
            "tech_score":            report["tech_score"],
            "conf_score":            report["conf_score"],
            "problem_score":         report["problem_score"],
            "hiring_recommendation": report["hiring_recommendation"],
            "strengths_summary":     report["strengths_summary"],
            "weaknesses_summary":    report["weaknesses_summary"],
            "roadmap":               report["roadmap"],
            "suggestion":            report["suggestion"],
            "suggested_answers":     report.get("suggested_answers", []),
            "total_questions":       len(answers_db),
        }

    except Exception as e:
        db.rollback()
        app.logger.error(f"v2_interview_finish error: {e}")
        return {"error": str(e)}, 500
    finally:
        db.close()


# ── Progress Tracking ────────────────────────────────────────────────────────
@app.route("/progress")
def progress():
    if "user" not in session:
        return redirect("/login")

    db = SessionLocal()
    sessions_data = []
    readiness_score = 0
    total_sessions = 0
    best_score = 0
    latest_score = 0

    try:
        found_user = db.query(models.User).filter_by(email=session["user"]).first()
        if found_user:
            reports_db = (
                db.query(models.InterviewSessionReport)
                .filter_by(user_id=found_user.id)
                .order_by(models.InterviewSessionReport.created_at.asc())
                .all()
            )
            total_sessions = len(reports_db)

            for r in reports_db:
                sessions_data.append({
                    "session_id": r.session_id,
                    "date": r.created_at.strftime("%b %d, %Y"),
                    "date_full": r.created_at.strftime("%Y-%m-%d %H:%M"),
                    "role": r.target_role,
                    "overall_score": r.overall_score,
                    "avg_comm": r.avg_comm or 0,
                    "avg_tech": r.avg_tech or 0,
                    "avg_conf": r.avg_conf or 0,
                    "avg_prob": r.avg_prob or 0,
                })

            if total_sessions > 0:
                best_score = max(r["overall_score"] for r in sessions_data)
                latest_score = sessions_data[-1]["overall_score"]
                # Readiness Score = rolling average of last 3 sessions
                last_3 = sessions_data[-3:]
                readiness_score = round(
                    sum(r["overall_score"] for r in last_3) / len(last_3)
                )
    except Exception as e:
        app.logger.error(f"Error loading progress data: {e}")
    finally:
        db.close()

    return render_template(
        "progress.html",
        user=session["user"],
        sessions=sessions_data,
        total_sessions=total_sessions,
        readiness_score=readiness_score,
        best_score=best_score,
        latest_score=latest_score,
    )


# ── Logout ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)