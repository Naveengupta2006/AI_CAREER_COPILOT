from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
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