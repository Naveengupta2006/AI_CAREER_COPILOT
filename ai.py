from openai import OpenAI
import json
import os
import logging
from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("NVIDIA_API_KEY"):
    raise RuntimeError("NVIDIA_API_KEY is not set in environment variables")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ.get("NVIDIA_API_KEY")
)

SYSTEM_PROMPT = """You are a senior software engineer, hiring manager, and ATS (Applicant Tracking System) expert.
Evaluate resumes thoroughly and return ONLY a valid JSON object — no markdown, no explanation.
Be strict and specific. Never give generic advice — base every point on the actual resume text provided."""


def analyze_resume(resume_text, user_goal, job_description=None):
    resume_text = resume_text[:8000].strip()
    jd_section = f'\nJob Description:\n{job_description[:4000].strip()}' if job_description else ""

    jd_instruction = (
        '"jd_match": {"score": 0, "matched_keywords": [], "missing_keywords": []},'
        if job_description else
        '"jd_match": null,'
    )

    user_message = f"""
User goal: "{user_goal}"

Resume:
{resume_text}
{jd_section}

Return ONLY this JSON, no other text:
{{
  "skills": [],
  "missing_skills": [],
  "roadmap": [],
  "interview_questions": [],
  "ats_score": 0,
  "resume_mistakes": [],
  "improvement_suggestions": [],
  "project_recommendations": [
    {{"title": "", "description": "", "tech_stack": [], "difficulty": "", "addresses_gap": ""}}
  ],
  {jd_instruction}
}}

Rules:
- skills: only relevant to the goal
- missing_skills: real gaps for this specific goal
- roadmap: ordered steps to close the gaps
- interview_questions: likely questions for this role
- ats_score: 0-100, based on formatting, keyword density, structure, and readability by ATS parsers
- resume_mistakes: specific issues found (e.g. "No quantified achievements", "Missing contact section")
- improvement_suggestions: specific, actionable fixes (not generic advice)
- project_recommendations: 3-4 portfolio projects, ordered easiest to hardest. First, analyze the user's existing projects on their resume (their tech stack, scale, complexity). Recommend new projects that explicitly build upon, scale up, or complement these existing projects (e.g. if they have a basic web app, recommend adding Redis caching, microservices, cloud deployment, CI/CD, or migrating to a more robust backend tech stack, rather than suggesting they build something from scratch that they have already done). Mix two types:
  (a) gap-filling projects that directly practice a skill listed in missing_skills
  (b) role-matching projects that mirror what someone in "{user_goal}" actually builds day to day
  For each: title (specific, not generic), description (2 sentences max, explain what it demonstrates and how it builds upon their existing projects),
  tech_stack (3-5 real tools/languages), difficulty (one of: "Beginner", "Intermediate", "Advanced"),
  addresses_gap (the specific missing_skill it targets, or "Role alignment" if it's a role-matching project)
- jd_match: ONLY fill this in if a job description was provided above. score = 0-100 overlap.
  matched_keywords = skills/terms present in both. missing_keywords = important JD terms absent from resume.
  If no job description was provided, leave jd_match as null.
"""

    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.choices[0].message.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found in response")

        return json.loads(content[start:end])

    except Exception as e:
        logging.error(f"AI error: {e}")
        return {
            "skills": [],
            "missing_skills": [],
            "roadmap": [],
            "interview_questions": [],
            "ats_score": 0,
            "resume_mistakes": [],
            "improvement_suggestions": [],
            "project_recommendations": [],
            "jd_match": None,
            "error": str(e)
        }