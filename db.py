import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/career_copilot")

# Ensure the URL is using postgresql:// for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def run_migrations():
    """Add new columns to existing tables safely (idempotent)."""
    new_columns = [
        ("interview_session_reports", "avg_comm", "INTEGER"),
        ("interview_session_reports", "avg_tech", "INTEGER"),
        ("interview_session_reports", "avg_conf", "INTEGER"),
        ("interview_session_reports", "avg_prob", "INTEGER"),
        # Phase 4 — AI Interviewer Logic
        ("interview_sessions", "candidate_name", "VARCHAR(255)"),
        ("interview_sessions", "chat_history",   "TEXT"),
        ("interview_sessions", "question_plan",  "TEXT"),
        ("interview_sessions", "current_q_idx",  "INTEGER DEFAULT 0"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in new_columns:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                ))
                conn.commit()
            except Exception:
                conn.rollback()