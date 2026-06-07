from flask import Flask, render_template, request, redirect, url_for, session    
from db import Base, engine, SessionLocal
from models import user, Reports
import PyPDF2
try:
    import docx
except ImportError:
    docx = None
import json

import models
from ai import analyze_resume


app = Flask(__name__)
app.secret_key = "Secret123"

Base.metadata.create_all(bind=engine)

#Home
@app.route("/")
def home():
    if "user" in session:
        return redirect('/dashboard')
    return redirect("/login")

# ----signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        db = SessionLocal()

        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")

            existing_user = db.query(models.user).filter_by(email=email).first()
            if existing_user:
                return "User already exists. Please log in."

            user = models.user(email=email, password=password)
            db.add(user)
            db.commit()

            return redirect("/login")
    return render_template("signup.html")


# login
@app.route("/login", methods=["GET", "POST"])
def login():
    db = SessionLocal()
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = db.query(models.user).filter_by(email=email, password=password).first()
        if user:
            session["user"] = user.email
            return redirect("/dashboard")
        else:
            return "Invalid credentials. Please try again."
    return render_template("login.html")

# DASHBOARD
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")
    result = None

    if request.method == "POST":
        user_goal = request.form.get("role")
        resume_text = request.form.get("resume_text")

        file = request.files.get("resume_file")

        #file handling
        if file and file.filename != "":
            if file.filename.endswith(".pdf"):
                try:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() or ""
                    resume_text = text
                except Exception as e:
                    result = {"error": f"PDF error: {str(e)}"}

            elif file.filename.endswith(".docx"):
                if docx is None:
                    result = {"error": "DOCX support not installed. Please upload a PDF instead."}
                else:
                    try:
                        doc = docx.Document(file)
                        text = ""
                        for para in doc.paragraphs:
                            text += para.text + "\n"
                        resume_text = text
                    except Exception as e:
                        result = {"error": f"DOCX error: {str(e)}"}
            else:
                return "Unsupported file format. Please upload a PDF or DOCX file."
    if resume_text and user_goal:
        try:
            result = analyze_resume(resume_text, user_goal)

            # save to db
            db = SessionLocal()
            user = db.query(models.User).filter_by(email=session["user"]).first()
            if user:
                report = models.Reports(user_id=user.id, goal=user_goal, resume_text=resume_text, analysis_result=json.dumps(result))
                db.add(report)
                db.commit()
        except Exception as e:
            result = {"error": f"Analysis error: {str(e)}"}

    return render_template("dashboard.html", result=result)

# history
@app.route("/history")
def history():
    if "user" not in session:
        return redirect("/login")
    
    db = SessionLocal()
    user = db.query(models.User).filter_by(email=session["user"]).first()

    reports = db.query(models.Reports).filter_by(user_id=user.id).all()


    passed_reports = []
    for report in reports:
        try:
            passed_result = json.loads(report.analysis_result)
        except Exception:
            passed_result = []

        passed_reports.append({
            "resume_text": report.resume_text,
            "analysis_result": passed_result
        })

    return render_template("history.html", history=passed_reports)


# logout route
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)

