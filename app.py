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

    return render_template("dashboard.html", analysis=analysis, user=session["user"])

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
    finally:
        db.close()

    return render_template("history.html", reports=passed_reports)

# ── Logout ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)