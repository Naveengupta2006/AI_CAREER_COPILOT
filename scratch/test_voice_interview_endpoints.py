import sys
import os
import json
import io

# Add the project root directory to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from db import SessionLocal
import models

def run_tests():
    print("Starting Voice Interview end-to-end integration tests...")
    
    # Disable CSRF for testing convenience
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True
    
    client = app.test_client()
    
    # 1. Sign up a test user
    email = "integration_test_user@example.com"
    password = "Password123"
    name = "Integration Test User"
    
    # Clean up user if already exists
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter_by(email=email).first()
        if existing:
            # Delete evaluations first due to foreign keys
            db.query(models.InterviewEvaluation).filter_by(user_id=existing.id).delete()
            db.query(models.Reports).filter_by(user_id=existing.id).delete()
            db.delete(existing)
            db.commit()
            print(f"Cleaned up existing test user: {email}")
    finally:
        db.close()
        
    signup_resp = client.post("/signup", data={
        "name": name,
        "email": email,
        "password": password
    }, follow_redirects=True)
    assert signup_resp.status_code == 200, f"Signup failed with status {signup_resp.status_code}"
    print("Step 1 Passed: User signup successful.")
    
    # 2. Log in the test user
    login_resp = client.post("/login", data={
        "email": email,
        "password": password
    }, follow_redirects=True)
    assert login_resp.status_code == 200, f"Login failed with status {login_resp.status_code}"
    print("Step 2 Passed: User login successful.")
    
    # 3. Upload a resume PDF to start voice interview prep session
    pdf_path = os.path.join(os.path.dirname(__file__), "dummy_resume.pdf")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Test PDF not found at: {pdf_path}")
        
    with open(pdf_path, "rb") as pdf_file:
        upload_data = {
            "role": "Staff Python Engineer",
            "file": (pdf_file, "dummy_resume.pdf")
        }
        # Flask test client uses multipart form-data when a file is included in dict
        upload_resp = client.post("/interview", data=upload_data, follow_redirects=True)
        
    assert upload_resp.status_code == 200, f"PDF upload failed with status {upload_resp.status_code}"
    print("Step 3 Passed: PDF Resume uploaded successfully.")
    
    # 4. Check if questions are correctly generated and stored in session
    with client.session_transaction() as sess:
        questions = sess.get("interview_questions")
        session_id = sess.get("interview_session_id")
        target_role = sess.get("interview_target_role")
        
        assert questions is not None, "interview_questions not found in session"
        assert len(questions) == 5, f"Expected 5 tailored questions, got {len(questions)}"
        assert session_id is not None, "session_id not found in session"
        assert target_role == "Staff Python Engineer", f"Expected Staff Python Engineer, got {target_role}"
        
        print(f"Step 4 Passed: Questions generated successfully by GPT-5/LLM. First question: '{questions[0]}'")
        print(f"Interview Session ID: {session_id}")
        
    # 5. Evaluate the candidate's answer for Question 1
    eval_payload = {
        "question": questions[0],
        "answer": "I have extensive experience building scalable web backends with Flask and Python, designing database schemas in PostgreSQL, and deploying them to production.",
        "target_role": target_role
    }
    
    eval_resp = client.post("/api/interview/evaluate", 
                            data=json.dumps(eval_payload),
                            content_type="application/json")
                            
    assert eval_resp.status_code == 200, f"Evaluation API failed with status {eval_resp.status_code}"
    eval_data = json.loads(eval_resp.data.decode("utf-8"))
    
    assert "score" in eval_data, "Evaluation missing score"
    assert "strong_points" in eval_data, "Evaluation missing strong_points"
    assert "improvements" in eval_data, "Evaluation missing improvements"
    assert "sample_answer" in eval_data, "Evaluation missing sample_answer"
    
    print(f"Step 5 Passed: Question 1 evaluated successfully.")
    print(f"Score: {eval_data['score']}/100")
    print(f"Strong points: {eval_data['strong_points']}")
    
    # 6. Verify database entry exists in PostgreSQL for this evaluation
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(email=email).first()
        assert user is not None, "User not found in DB"
        
        evaluations = db.query(models.InterviewEvaluation).filter_by(user_id=user.id, session_id=session_id).all()
        assert len(evaluations) == 1, f"Expected 1 evaluation in database, found {len(evaluations)}"
        
        db_eval = evaluations[0]
        assert db_eval.question == questions[0], "Stored question mismatch"
        assert db_eval.answer == eval_payload["answer"], "Stored answer mismatch"
        
        stored_result = json.loads(db_eval.evaluation_result)
        assert stored_result["score"] == eval_data["score"], "Stored score mismatch"
        
        print("Step 6 Passed: Stored evaluation committed and verified in PostgreSQL database successfully.")
    finally:
        db.close()
        
    # 7. Reset the session and verify session is cleared
    reset_resp = client.get("/interview/reset", follow_redirects=True)
    assert reset_resp.status_code == 200, f"Reset endpoint failed with status {reset_resp.status_code}"
    
    with client.session_transaction() as sess:
        assert "interview_questions" not in sess, "interview_questions should be cleared"
        assert "interview_target_role" not in sess, "interview_target_role should be cleared"
        assert "interview_session_id" not in sess, "interview_session_id should be cleared"
        
    print("Step 7 Passed: Reset / New Session successfully cleared the session variables.")
    print("\nAll Voice Interview feature integration tests PASSED successfully!")

if __name__ == "__main__":
    run_tests()
