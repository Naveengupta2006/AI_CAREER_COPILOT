from sqlalchemy import Column, Integer, String, Text, ForeignKey
from db import Base

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