from openai import OpenAI
import json
import os
import logging
from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("NVIDIA_API_KEY"):
    raise RuntimeError("NVIDIA_API_KEY is not set in environment variables")

client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = os.environ.get("NVIDIA_API_KEY", "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")
)

SYSTEM_PROMPT = """You are a senior software engineer and hiring manager.
Evaluate resumes and return ONLY a valid JSON object — no markdown, no explanation.
Be strict: extract only skills relevant to the user's goal."""

def analyze_resume(resume_text, user_goal):
    resume_text = resume_text[:8000].strip()

    user_message = f"""
User goal: "{user_goal}"

Resume:
{resume_text}

Return ONLY this JSON, no other text:
{{
  "skills": [],
  "missing_skills": [],
  "roadmap": [],
  "interview_questions": []
}}

Rules:
- skills: only relevant to the goal
- missing_skills: real gaps for this role
- roadmap: ordered steps to close the gaps
- interview_questions: likely questions for this role
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message}
            ],
            max_tokens=1500,
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        start = content.find("{")
        end = content.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("No JSON object found in response")

        return json.loads(content[start:end])

    except Exception as e:
        logging.error(f"AI analysis error: {e}")
        return {
            "skills": [],
            "missing_skills": [],
            "roadmap": [],
            "interview_questions": [],
            "error": str(e)
        }