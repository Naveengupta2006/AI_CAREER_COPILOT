import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal
import models

db = SessionLocal()
try:
    sessions = db.query(models.InterviewSession).all()
    print(f"Total sessions: {len(sessions)}")
    for i, s in enumerate(sessions):
        print(f"Session {i+1} (ID: {s.id}):")
        print(f"Role: {s.role}")
        print(f"Resume text preview:\n{repr(s.resume_text[:200]) if s.resume_text else 'None'}")
        print("-" * 50)
finally:
    db.close()
