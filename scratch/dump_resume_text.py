import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal
import models

db = SessionLocal()
try:
    report = db.query(models.Reports).first()
    if report:
        print("Dumping resume text...")
        with open("scratch/dumped_resume.txt", "w", encoding="utf-8") as f:
            f.write(report.resume_text)
        print("Done. Saved to scratch/dumped_resume.txt")
    else:
        print("No reports found")
finally:
    db.close()
