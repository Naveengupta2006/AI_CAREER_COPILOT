from openai import OpenAI
import json
import os
import logging
import re
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


def extract_and_parse_json(content, fallback_val=None):
    """
    Robustly extracts and parses a JSON object from LLM response content.
    Tries multiple extraction strategies and strips potential JSON syntax hazards.
    """
    if not content:
        logging.warning("Empty content passed to extract_and_parse_json")
        return fallback_val

    content_str = content.strip()
    
    # Strategy 1: Try parsing the raw content directly
    try:
        return json.loads(content_str)
    except Exception:
        pass

    # Strategy 2: Extract content from markdown code blocks
    # Handle both ```json and ```
    for block_marker in ["```json", "```JSON", "```"]:
        if block_marker in content_str:
            try:
                parts = content_str.split(block_marker)
                if len(parts) > 1:
                    inner = parts[1].split("```")[0].strip()
                    return json.loads(inner)
            except Exception:
                pass

    # Strategy 3: Find the first '{' and last '}'
    start = content_str.find("{")
    end = content_str.rfind("}") + 1
    if start != -1 and end > start:
        json_candidate = content_str[start:end]
        try:
            return json.loads(json_candidate)
        except Exception as e:
            # Let's try cleaning simple JSON errors:
            # 1. Trailing commas in lists/objects
            # 2. Simple single line comments (// ...)
            try:
                # Remove single-line comments
                cleaned = re.sub(r'^\s*//.*$', '', json_candidate, flags=re.MULTILINE)
                cleaned = re.sub(r'\s*//.*$', '', cleaned)
                # Remove trailing commas before closing braces/brackets
                cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)
                return json.loads(cleaned)
            except Exception as clean_err:
                logging.error(f"Failed to parse cleaned JSON candidate: {clean_err}")
                logging.error(f"Original parsing error: {e}")

    # Log the failure and the raw content for debugging
    logging.error("Failed to extract valid JSON from LLM response.")
    logging.error(f"Raw completion content was:\\n{content}")
    return fallback_val


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

        parsed = extract_and_parse_json(content)
        if parsed is None:
            raise ValueError("No JSON found in response")
        return parsed

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


def evaluate_interview_answer(question, answer, target_role="Software Engineer"):
    """
    Evaluates the interviewee's answer to a given interview question using LLM (GPT-5 Interviewer).
    """
    evaluation_prompt = f"""
    You are GPT-5, a world-class hiring manager and mock interviewer evaluating a candidate for the role: "{target_role}".
    
    Evaluate the candidate's response to the following interview question:
    
    Question: "{question}"
    Candidate's Answer: "{answer}"
    
    Be constructive, professional, and thorough. 
    Return ONLY a valid, parseable JSON object matching the format below.
    Do NOT include any comments (like '//' or '/* ... */') inside the JSON.
    Do NOT include any trailing commas.
    Do NOT wrap the JSON in markdown code blocks.
    
    Format:
    {{
      "score": 85,
      "strong_points": [
        "Point 1...",
        "Point 2..."
      ],
      "improvements": [
        "Improvement 1...",
        "Improvement 2..."
      ],
      "sample_answer": "Model response..."
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a professional mock interviewer and return ONLY JSON."},
                {"role": "user", "content": evaluation_prompt}
            ],
            temperature=0.3,
            max_tokens=1500,
        )
        content = response.choices[0].message.content.strip()
        
        parsed = extract_and_parse_json(content)
        if parsed is None:
            raise ValueError("No JSON found in response")
        return parsed
    except Exception as e:
        logging.error(f"Evaluation AI error: {e}")
        return {
            "score": 0,
            "strong_points": ["Could not evaluate response due to system error."],
            "improvements": [str(e)],
            "sample_answer": "Error retrieving sample answer."
        }


def generate_tailored_questions(resume_text, target_role="Software Engineer"):
    """
    Generates 5 tailored interview questions based on the candidate's resume and target role.
    """
    resume_text = resume_text[:8000].strip()
    prompt = f"""
    You are GPT-5, an elite hiring manager and interviewer for the role: "{target_role}".
    Based on the candidate's resume below, generate exactly 5 tailored interview questions.
    Mix technical questions about their projects/skills and behavioral questions about their experience.
    Make the questions highly specific to the technologies and experience listed in their resume.
    
    Candidate Resume:
    {resume_text}
    
    Return ONLY a valid JSON object matching the format below.
    Do NOT include any markdown code blocks, explanation, or text outside the JSON.
    
    Format:
    {{
      "questions": [
        "Question 1...",
        "Question 2...",
        "Question 3...",
        "Question 4...",
        "Question 5..."
      ]
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a professional mock interviewer and return ONLY JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=1000,
        )
        content = response.choices[0].message.content.strip()
        
        parsed = extract_and_parse_json(content)
        if parsed is None:
            raise ValueError("No JSON found in response")
        return parsed.get("questions", [])
    except Exception as e:
        logging.error(f"Generate questions error: {e}")
        # Curated fallback questions based on target role
        return [
            f"Tell me about a complex project you built as a {target_role} and the technical decisions you made.",
            f"What specific skills or tools from your resume make you a strong fit for a {target_role} role?",
            "Describe a challenging bug or issue you encountered in your projects and how you diagnosed it.",
            "How do you keep up with new technologies and industry developments in your domain?",
            "Explain a scenario where you had to collaborate under tight deadlines or ambiguous requirements."
        ]


def generate_session_feedback_report(evaluations, target_role="Software Engineer"):
    """
    Aggregates all question-answer evaluations of the session and generates
    overarching feedback (summary and action plan) via GPT-5.
    """
    formatted_evals = []
    for idx, ev in enumerate(evaluations):
        formatted_evals.append(f"""
Question {idx+1}: "{ev.get('question')}"
Candidate's Answer: "{ev.get('answer')}"
Score: {ev.get('score', 0)}/100
Strong Points: {ev.get('strong_points', [])}
Improvements: {ev.get('improvements', [])}
""")
    
    evals_text = "\n---\n".join(formatted_evals)
    
    prompt = f"""
    You are GPT-5, an elite executive coach and technical hiring director.
    Analyze the candidate's performance across all questions in this mock interview session for the role: "{target_role}".
    
    Here is the detailed summary of questions, candidate answers, and individual evaluations:
    {evals_text}
    
    Synthesize this information into a high-level overarching performance feedback report.
    Return ONLY a valid, parseable JSON object matching the format below.
    Do NOT include any comments (like '//' or '/* ... */') inside the JSON.
    Do NOT include any trailing commas.
    Do NOT wrap the JSON in markdown code blocks.
    
    Format:
    {{
      "summary": "Overall synthesis review of candidate performance and role readiness.",
      "action_plan": [
        "Action plan advice item 1...",
        "Action plan advice item 2...",
        "Action plan advice item 3..."
      ]
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a professional hiring director and return ONLY JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=1500,
        )
        content = response.choices[0].message.content.strip()
        
        parsed = extract_and_parse_json(content)
        if parsed is None:
            raise ValueError("No JSON found in response")
        return parsed
    except Exception as e:
        logging.error(f"Generate session feedback report error: {e}")
        return {
            "summary": "An overarching synthesis could not be compiled due to a system error. Please review the individual question breakdowns below for detailed feedback.",
            "action_plan": [
                "Review individual improvement areas listed for each question.",
                "Continue practicing with different mock interview questions.",
                "Consult the recommended ideal model answers for each question."
            ]
        }