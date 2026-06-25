import sys
import os
import json

# Add the project root directory to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from db import SessionLocal
import models

def run_tests():
    print("Starting Session Feedback Aggregation integration tests...")
    
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True
    
    client = app.test_client()
    
    email = "report_test_user@example.com"
    password = "Password123"
    name = "Report Test User"
    
    # 1. Database Cleanup
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter_by(email=email).first()
        if existing:
            db.query(models.InterviewSessionReport).filter_by(user_id=existing.id).delete()
            db.query(models.InterviewEvaluation).filter_by(user_id=existing.id).delete()
            db.query(models.Reports).filter_by(user_id=existing.id).delete()
            db.delete(existing)
            db.commit()
            print(f"Cleaned up existing test user: {email}")
    finally:
        db.close()

    # 2. Signup & Login
    signup_resp = client.post("/signup", data={"name": name, "email": email, "password": password}, follow_redirects=True)
    assert signup_resp.status_code == 200, "Signup failed"
    
    login_resp = client.post("/login", data={"email": email, "password": password}, follow_redirects=True)
    assert login_resp.status_code == 200, "Login failed"
    print("User registered and logged in successfully.")
    
    # 3. PDF Resume Upload
    pdf_path = os.path.join(os.path.dirname(__file__), "dummy_resume.pdf")
    with open(pdf_path, "rb") as pdf_file:
        upload_resp = client.post("/interview", data={
            "role": "Staff Python Engineer",
            "file": (pdf_file, "dummy_resume.pdf")
        }, follow_redirects=True)
    assert upload_resp.status_code == 200, "PDF upload failed"
    
    with client.session_transaction() as sess:
        questions = sess.get("interview_questions")
        session_id = sess.get("interview_session_id")
        target_role = sess.get("interview_target_role")
        
        assert questions is not None
        assert session_id is not None
        
    print(f"Resume text uploaded and session questions generated successfully. Session ID: {session_id}")

    # 4. Evaluate two questions
    eval_answers = [
        "I have extensive experience building high-throughput Flask APIs and implementing optimized PostgreSQL query indexing.",
        "For styling, I prefer custom CSS properties and responsive grids to keep interfaces responsive and load times low."
    ]
    
    for idx in range(2):
        eval_payload = {
            "question": questions[idx],
            "answer": eval_answers[idx],
            "target_role": target_role
        }
        eval_resp = client.post("/api/interview/evaluate", 
                                data=json.dumps(eval_payload),
                                content_type="application/json")
        assert eval_resp.status_code == 200, f"Evaluation API failed for question {idx+1}"
        print(f"Answer for Question {idx+1} evaluated successfully.")
        
    # 5. Fetch Session Report
    report_url = f"/interview/report/{session_id}"
    report_resp = client.get(report_url)
    assert report_resp.status_code == 200, f"Fetch report page failed with status {report_resp.status_code}"
    
    html_content = report_resp.data.decode("utf-8")
    assert "Mock Interview Session Feedback" in html_content, "Report page title missing"
    assert "GPT-5 Interview Synthesis" in html_content, "GPT-5 Summary block missing"
    assert "Tailored Development Roadmap" in html_content, "Development Roadmap block missing"
    print("Report HTML page generated and elements verified successfully.")

    # 6. Verify Database Caching
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(email=email).first()
        report_row = db.query(models.InterviewSessionReport).filter_by(user_id=user.id, session_id=session_id).first()
        
        assert report_row is not None, "Report row not committed to PostgreSQL database"
        assert report_row.overall_score > 0, f"Expected positive score, got {report_row.overall_score}"
        assert len(report_row.summary) > 20, "Aggregated summary is too short"
        
        action_plan = json.loads(report_row.action_plan)
        assert len(action_plan) > 0, "Aggregated action plan list is empty"
        
        print("Database verification passed: report is committed to PostgreSQL database correctly.")
        print(f"Overall Score: {report_row.overall_score}/100")
        print(f"Generated Summary: {report_row.summary}")
        print(f"Generated Roadmap Actions: {action_plan}")
    finally:
        db.close()

    # 7. Check History Page lists the session report
    history_resp = client.get("/history")
    assert history_resp.status_code == 200, "History page fetch failed"
    history_html = history_resp.data.decode("utf-8")
    
    assert session_id in history_html, "Interview report session ID not found on History page"
    assert "View Full Feedback Report" in history_html, "Action link to full report missing in history"
    print("History page listing verified successfully.")
    
    print("\nAll feedback aggregation and reporting integration tests PASSED successfully!")

if __name__ == "__main__":
    run_tests()
