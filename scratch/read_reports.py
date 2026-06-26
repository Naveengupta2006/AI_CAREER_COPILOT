import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal
import models

db = SessionLocal()
try:
    reports = db.query(models.Reports).all()
    print(f"Total reports: {len(reports)}")
    for i, r in enumerate(reports):
        print(f"Report {i+1}:")
        print(f"Goal: {r.goal}")
        print(f"Resume text preview:\n{repr(r.resume_text[:300])}")
        print("-" * 50)
finally:
    db.close()
