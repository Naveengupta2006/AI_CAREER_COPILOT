import sys
import os
import datetime

# Add the project root directory to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from db import SessionLocal
import models

def run_tests():
    print("Starting Mock Interview Progress Analytics integration tests...")
    
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True
    
    client = app.test_client()
    
    email = "analytics_test_user@example.com"
    password = "Password123"
    name = "Analytics Test User"
    
    # 1. Cleanup old records for this user
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter_by(email=email).first()
        if existing:
            db.query(models.InterviewSessionReport).filter_by(user_id=existing.id).delete()
            db.query(models.InterviewEvaluation).filter_by(user_id=existing.id).delete()
            db.query(models.Reports).filter_by(user_id=existing.id).delete()
            db.delete(existing)
            db.commit()
            print(f"Cleaned up existing analytics test user: {email}")
    finally:
        db.close()

    # 2. Signup and Login
    signup_resp = client.post("/signup", data={"name": name, "email": email, "password": password}, follow_redirects=True)
    assert signup_resp.status_code == 200, "Signup failed"
    
    login_resp = client.post("/login", data={"email": email, "password": password}, follow_redirects=True)
    assert login_resp.status_code == 200, "Login failed"
    print("User registered and logged in successfully.")

    # 3. Create simulated interview session reports
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(email=email).first()
        assert user is not None
        
        # We simulate 3 sessions with distinct dates and scores
        sessions = [
            {
                "session_id": "session-1",
                "role": "Senior Python Engineer",
                "score": 65,
                "date": datetime.datetime(2026, 6, 20, 10, 0, 0)
            },
            {
                "session_id": "session-2",
                "role": "Staff Python Engineer",
                "score": 72,
                "date": datetime.datetime(2026, 6, 22, 11, 30, 0)
            },
            {
                "session_id": "session-3",
                "role": "Lead Python Architect",
                "score": 85,
                "date": datetime.datetime(2026, 6, 25, 14, 15, 0)
            }
        ]
        
        for idx, s in enumerate(sessions):
            session_report = models.InterviewSessionReport(
                user_id=user.id,
                session_id=s["session_id"],
                target_role=s["role"],
                overall_score=s["score"],
                summary=f"Mock summary for session {idx+1}",
                action_plan='["Action step 1", "Action step 2"]',
                created_at=s["date"]
            )
            db.add(session_report)
        db.commit()
        print("Successfully committed 3 simulated interview session reports with scores: 65, 72, 85.")
    finally:
        db.close()

    # 4. Request GET /dashboard and verify analytics context
    dash_resp = client.get("/dashboard")
    assert dash_resp.status_code == 200, f"Dashboard loading failed with status {dash_resp.status_code}"
    
    html_content = dash_resp.data.decode("utf-8")
    
    # Verify metrics appear
    assert "Total Sessions" in html_content, "Total Sessions metric label missing"
    assert "Average Score" in html_content, "Average Score metric label missing"
    assert "Latest Score" in html_content, "Latest Score metric label missing"
    
    # Verify calculated values in metrics
    # Total sessions: 3
    assert ">3</h3>" in html_content, "Incorrect total sessions metric value"
    # Average score: round((65 + 72 + 85) / 3) = 74
    assert ">74</h3>" in html_content, "Incorrect average score metric value"
    # Latest score: 85
    assert ">85</h3>" in html_content, "Incorrect latest score metric value"
    
    # Verify Chart.js configurations in JS scripts
    assert "scoreTrendChart" in html_content, "Chart canvas element missing"
    assert '["Jun 20, 2026", "Jun 22, 2026", "Jun 25, 2026"]' in html_content, "Chart.js labels dataset mismatch"
    assert "[65, 72, 85]" in html_content, "Chart.js scores dataset mismatch"
    assert '["Senior Python Engineer", "Staff Python Engineer", "Lead Python Architect"]' in html_content, "Chart.js roles dataset mismatch"
    
    print("Dashboard analytics calculations and script variables verified successfully!")
    print("\nAll progress tracking dashboard integration tests PASSED successfully!")

if __name__ == "__main__":
    run_tests()
