import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal
import models

def fix_text(text):
    if not text:
        return text
    replacements = {
        "ritikgupta8130@gmail.comRitik Gupta": "ritikgupta8130@gmail.com\nRitik Gupta",
        "Social Media MarketingPortfolio": "Social Media Marketing\nPortfolio",
        "SEO & MarketingKeyword Research": "SEO & Marketing\nKeyword Research",
        "Content & CopywritingContent Writing": "Content & Copywriting\nContent Writing",
        "CMSWordPress": "CMS\nWordPress",
        "Digital MarketingSocial Media Marketing": "Digital Marketing\nSocial Media Marketing",
        "Tools & AnalyticsGoogle Search Console": "Tools & Analytics\nGoogle Search Console"
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

db = SessionLocal()
try:
    # 1. Update Reports table
    reports = db.query(models.Reports).all()
    updated_reports = 0
    for r in reports:
        new_text = fix_text(r.resume_text)
        if new_text != r.resume_text:
            r.resume_text = new_text
            updated_reports += 1
            
    # 2. Update InterviewSession table
    sessions = db.query(models.InterviewSession).all()
    updated_sessions = 0
    for s in sessions:
        new_text = fix_text(s.resume_text)
        if new_text != s.resume_text:
            s.resume_text = new_text
            updated_sessions += 1
            
    db.commit()
    print(f"Migration completed successfully!")
    print(f"Updated {updated_reports} rows in reports table.")
    print(f"Updated {updated_sessions} rows in interview_sessions table.")
except Exception as e:
    db.rollback()
    print(f"Migration failed: {e}")
finally:
    db.close()
