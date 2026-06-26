from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float, Boolean
from db import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id       = Column(Integer, primary_key=True)
    name     = Column(String(255), nullable=False)
    email    = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)

class Reports(Base):
    __tablename__ = "reports"

    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False)
    goal            = Column(String(255))
    resume_text     = Column(Text)
    analysis_result = Column(Text)

class InterviewEvaluation(Base):
    __tablename__ = "interview_evaluations"

    id                = Column(Integer, primary_key=True)
    user_id           = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id        = Column(String(255), nullable=False)
    question          = Column(Text, nullable=False)
    answer            = Column(Text, nullable=False)
    evaluation_result = Column(Text, nullable=False)
    created_at        = Column(DateTime, default=datetime.datetime.utcnow)

class InterviewSessionReport(Base):
    __tablename__ = "interview_session_reports"

    id                = Column(Integer, primary_key=True)
    user_id           = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id        = Column(String(255), unique=True, nullable=False)
    target_role       = Column(String(255), nullable=False)
    overall_score     = Column(Integer, nullable=False)
    summary           = Column(Text, nullable=False)
    action_plan       = Column(Text, nullable=False)
    created_at        = Column(DateTime, default=datetime.datetime.utcnow)
    # Sub-score columns (added for Progress Tracking)
    avg_comm          = Column(Integer, nullable=True)
    avg_tech          = Column(Integer, nullable=True)
    avg_conf          = Column(Integer, nullable=True)
    avg_prob          = Column(Integer, nullable=True)


# ── Phase 1: New Interview Pipeline ───────────────────────────────────────────

class InterviewSession(Base):
    """
    Root entity for a single end-to-end interview session.
    Stores session-level metadata and aggregated scores.
    """
    __tablename__ = "interview_sessions"

    id                     = Column(Integer, primary_key=True)
    user_id                = Column(Integer, ForeignKey("users.id"), nullable=False)
    role                   = Column(String(255), nullable=False)
    resume_text            = Column(Text, nullable=True)
    overall_score          = Column(Float, nullable=True)          # 0–100, set after session ends
    comm_score             = Column(Float, nullable=True)          # Communication
    tech_score             = Column(Float, nullable=True)          # Technical Knowledge
    conf_score             = Column(Float, nullable=True)          # Confidence
    problem_score          = Column(Float, nullable=True)          # Problem Solving
    hiring_recommendation  = Column(String(50), nullable=True)     # e.g. "Strong Hire", "No Hire"
    created_at             = Column(DateTime, default=datetime.datetime.utcnow)

    # ── Phase 4: AI Interviewer Logic ────────────────────────────────
    candidate_name = Column(String(255), nullable=True)   # pulled from User.name at session start
    chat_history   = Column(Text,        nullable=True)   # JSON list of {role, content} messages
    question_plan  = Column(Text,        nullable=True)   # JSON list of {type, topic_hint} — 10 entries
    current_q_idx  = Column(Integer,     default=0)       # 0-based pointer into question_plan


class InterviewAnswer(Base):
    """
    One row per question answered inside an InterviewSession.
    Stores the transcript, per-question score (0–10), and AI feedback.
    """
    __tablename__ = "interview_answers"

    id              = Column(Integer, primary_key=True)
    session_id      = Column(Integer, ForeignKey("interview_sessions.id"), nullable=False)
    question_text   = Column(Text, nullable=False)
    question_type   = Column(String(100), nullable=True)   # e.g. "behavioral", "technical"
    answer_text     = Column(Text, nullable=True)          # speech-to-text transcript
    score           = Column(Float, nullable=True)         # 0–10
    strengths       = Column(Text, nullable=True)          # JSON array stored as text
    weaknesses      = Column(Text, nullable=True)          # JSON array stored as text
    follow_up_asked = Column(Boolean, default=False)
    comm_score      = Column(Float, nullable=True)         # Communication 0-10
    tech_score      = Column(Float, nullable=True)         # Technical 0-10
    conf_score      = Column(Float, nullable=True)         # Confidence 0-10
    problem_score   = Column(Float, nullable=True)         # Problem Solving 0-10


class InterviewReport(Base):
    """
    End-of-session AI-generated summary report (1-to-1 with InterviewSession).
    """
    __tablename__ = "interview_reports"

    id                  = Column(Integer, primary_key=True)
    session_id          = Column(Integer, ForeignKey("interview_sessions.id"), unique=True, nullable=False)
    strengths_summary   = Column(Text, nullable=True)   # prose or JSON
    weaknesses_summary  = Column(Text, nullable=True)
    roadmap             = Column(Text, nullable=True)   # JSON array of improvement steps
    suggestion          = Column(Text, nullable=True)   # overall coaching advice
    suggested_answers   = Column(Text, nullable=True)   # JSON array of rewritten weak answers
    created_at          = Column(DateTime, default=datetime.datetime.utcnow)