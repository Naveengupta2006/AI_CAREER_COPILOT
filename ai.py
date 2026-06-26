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
        return json.loads(content_str, strict=False)
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
                    return json.loads(inner, strict=False)
            except Exception:
                pass

    # Strategy 3: Find the first '{' and last '}'
    start = content_str.find("{")
    end = content_str.rfind("}") + 1
    if start != -1 and end > start:
        json_candidate = content_str[start:end]
        try:
            return json.loads(json_candidate, strict=False)
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
                return json.loads(cleaned, strict=False)
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
    You are a world-class hiring manager and mock interviewer evaluating a candidate for the role: "{target_role}".
    
    Evaluate the candidate's response to the following interview question:
    
    Question: {question}
    Candidate's Answer: {answer}
    
    Be constructive, professional, and thorough. 
    You MUST return ONLY a valid JSON object. Do not include any text outside the JSON.
    CRITICAL: Any line breaks or newlines within JSON string values MUST be escaped as \\n. NEVER use literal unescaped newlines inside strings.
    
    Required JSON Format:
    {{
      "communication_score": 85,
      "technical_score": 80,
      "confidence_score": 90,
      "problem_solving_score": 85,
      "strong_points": ["Point 1", "Point 2"],
      "improvements": ["Improvement 1", "Improvement 2"],
      "sample_answer": "Here is an ideal response..."
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a JSON-only API. You must return only a valid JSON object starting with { and ending with }."},
                {"role": "user", "content": evaluation_prompt}
            ],
            temperature=0.2,
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
            "communication_score": 0,
            "technical_score": 0,
            "confidence_score": 0,
            "problem_solving_score": 0,
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
      "top_strengths": [
        "Strength 1...",
        "Strength 2...",
        "Strength 3..."
      ],
      "top_weaknesses": [
        "Weakness 1...",
        "Weakness 2...",
        "Weakness 3..."
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
            "top_strengths": [
                "Review individual improvement areas listed for each question."
            ],
            "top_weaknesses": [
                "Review individual improvement areas listed for each question."
            ]
        }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — AI Helpers
# ─────────────────────────────────────────────────────────────────────────────

def generate_interview_question(role: str, resume_text: str, asked_questions: list, question_number: int) -> dict:
    """
    Generate the next interview question for an InterviewSession.
    Returns {"question_text": str, "question_type": str}
    question_type is one of: "behavioral", "technical", "situational", "resume_based"
    """
    asked_block = ""
    if asked_questions:
        asked_block = "Questions already asked (do NOT repeat or rephrase these):\n" + \
                      "\n".join(f"- {q}" for q in asked_questions)

    prompt = f"""You are an elite technical recruiter conducting a real job interview for: "{role}".
Question #{question_number} out of a planned 5.

Candidate resume summary (first 3000 chars):
{resume_text[:3000].strip()}

{asked_block}

Generate exactly ONE new, highly specific interview question.
Alternate between question types to get a complete picture of the candidate.
Return ONLY valid JSON — no markdown, no extra text:
{{
  "question_text": "Your question here?",
  "question_type": "behavioral" | "technical" | "situational" | "resume_based"
}}
"""
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a JSON-only API. Return exactly one JSON object."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.5,
            max_tokens=300,
        )
        parsed = extract_and_parse_json(response.choices[0].message.content)
        if parsed and parsed.get("question_text"):
            return parsed
    except Exception as e:
        logging.error(f"generate_interview_question error: {e}")

    # Fallback
    fallback_q = [
        f"Tell me about a project from your resume that you are most proud of and why it is relevant to {role}.",
        f"What does a typical debugging session look like for you in your day-to-day work?",
        f"Describe a time you had to learn a new technology quickly under pressure.",
        f"How do you approach code reviews — both giving and receiving feedback?",
        f"Walk me through how you would design a scalable REST API from scratch.",
    ]
    return {
        "question_text": fallback_q[min(question_number - 1, len(fallback_q) - 1)],
        "question_type": "behavioral"
    }


def evaluate_answer_phase2(question_text: str, answer_text: str, question_type: str, role: str) -> dict:
    """
    Evaluate one answer. Returns:
    {
      "comm_score":    0-10,
      "tech_score":    0-10,
      "conf_score":    0-10,
      "problem_score": 0-10,
      "overall_score": 0-10,
      "strengths":     [...],
      "weaknesses":    [...],
      "follow_up_needed": true/false,
      "follow_up_reason": "why a follow-up is needed"
    }
    """
    prompt = f"""You are a senior hiring manager evaluating a candidate for: "{role}".
Question type: {question_type}

Question: {question_text}

Candidate's answer: {answer_text}

Score each dimension strictly on a 0–10 scale (10 = exceptional).
Decide if a follow-up question is needed (true only if the answer was vague, incomplete, or evasive).

Return ONLY valid JSON — no markdown, no extra text:
{{
  "comm_score":       7,
  "tech_score":       6,
  "conf_score":       8,
  "problem_score":    7,
  "overall_score":    7,
  "strengths":        ["Specific strength 1", "Specific strength 2"],
  "weaknesses":       ["Specific area to improve 1"],
  "follow_up_needed": false,
  "follow_up_reason": ""
}}
"""
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a JSON-only API. Return exactly one JSON object."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.2,
            max_tokens=600,
        )
        parsed = extract_and_parse_json(response.choices[0].message.content)
        if parsed:
            # Clamp all numeric scores to [0, 10]
            for key in ("comm_score", "tech_score", "conf_score", "problem_score", "overall_score"):
                if key in parsed:
                    parsed[key] = max(0, min(10, float(parsed[key])))
            return parsed
    except Exception as e:
        logging.error(f"evaluate_answer_phase2 error: {e}")

    return {
        "comm_score": 5, "tech_score": 5, "conf_score": 5, "problem_score": 5,
        "overall_score": 5, "strengths": [], "weaknesses": ["Evaluation unavailable."],
        "follow_up_needed": False, "follow_up_reason": ""
    }


def generate_follow_up_question(original_question: str, answer_text: str, follow_up_reason: str, role: str) -> dict:
    """
    Generate a targeted follow-up question based on an incomplete/vague answer.
    Returns {"question_text": str, "question_type": "follow_up"}
    """
    prompt = f"""You are a senior interviewer for: "{role}".

The candidate gave an incomplete or vague answer. Generate ONE concise follow-up question
that directly probes the gap identified below.

Original question: {original_question}
Candidate answer:  {answer_text}
Gap to probe:      {follow_up_reason}

Return ONLY valid JSON — no markdown:
{{
  "question_text": "Follow-up question here?",
  "question_type": "follow_up"
}}
"""
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a JSON-only API. Return exactly one JSON object."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200,
        )
        parsed = extract_and_parse_json(response.choices[0].message.content)
        if parsed and parsed.get("question_text"):
            return parsed
    except Exception as e:
        logging.error(f"generate_follow_up_question error: {e}")

    return {
        "question_text": f"Can you elaborate further on that point?",
        "question_type": "follow_up"
    }


def generate_final_report_phase2(session_answers: list, role: str) -> dict:
    """
    Aggregate all per-answer evaluations into a final report.
    Returns:
    {
      "overall_score":         0-100,
      "comm_score":            0-100,
      "tech_score":            0-100,
      "conf_score":            0-100,
      "problem_score":         0-100,
      "hiring_recommendation": str,
      "strengths_summary":     str,
      "weaknesses_summary":    str,
      "roadmap":               [...],
      "suggestion":            str
    }
    """
    if not session_answers:
        return {
            "overall_score": 0, "comm_score": 0, "tech_score": 0,
            "conf_score": 0, "problem_score": 0,
            "hiring_recommendation": "Insufficient Data",
            "strengths_summary": "", "weaknesses_summary": "",
            "roadmap": [], "suggestion": "No answers were recorded in this session."
        }

    # Build a text summary of all Q&A pairs for the LLM
    qa_lines = []
    for i, ans in enumerate(session_answers, 1):
        qa_lines.append(
            f"Q{i} [{ans.get('question_type','?')}]: {ans.get('question_text','')}\n"
            f"  Answer: {ans.get('answer_text','(no answer)')[:500]}\n"
            f"  Scores → Comm:{ans.get('comm_score',0)} Tech:{ans.get('tech_score',0)} "
            f"Conf:{ans.get('conf_score',0)} Prob:{ans.get('problem_score',0)}\n"
            f"  Strengths: {ans.get('strengths',[])}\n"
            f"  Weaknesses: {ans.get('weaknesses',[])}"
        )
    qa_block = "\n\n".join(qa_lines)

    # Compute raw averages (0-10 scale → 0-100 after × 10)
    def avg(key):
        vals = [a.get(key, 0) for a in session_answers if a.get(key) is not None]
        return round((sum(vals) / len(vals)) * 10) if vals else 0

    raw_comm    = avg("comm_score")
    raw_tech    = avg("tech_score")
    raw_conf    = avg("conf_score")
    raw_prob    = avg("problem_score")
    raw_overall = round((raw_comm + raw_tech + raw_conf + raw_prob) / 4)

    if raw_overall >= 80:
        default_rec = "Strong Hire"
    elif raw_overall >= 65:
        default_rec = "Hire"
    elif raw_overall >= 50:
        default_rec = "Lean No Hire"
    else:
        default_rec = "No Hire"

    prompt = f"""You are an executive technical hiring director for the role: "{role}".

Below is the complete Q&A transcript with per-answer scores from a mock interview session:

{qa_block}

Write a concise, honest final debrief. Return ONLY valid JSON — no markdown:
{{
  "hiring_recommendation": "Strong Hire" | "Hire" | "Lean No Hire" | "No Hire",
  "strengths_summary":   "2–3 sentence prose summary of the candidate's top strengths.",
  "weaknesses_summary":  "2–3 sentence prose summary of the key areas to improve.",
  "roadmap": [
    "Actionable improvement step 1",
    "Actionable improvement step 2",
    "Actionable improvement step 3"
  ],
  "suggestion": "One-paragraph overall coaching advice for this candidate."
}}
"""
    try:
        response = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a JSON-only API. Return exactly one JSON object."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1200,
        )
        parsed = extract_and_parse_json(response.choices[0].message.content)
        if parsed:
            return {
                "overall_score":         raw_overall,
                "comm_score":            raw_comm,
                "tech_score":            raw_tech,
                "conf_score":            raw_conf,
                "problem_score":         raw_prob,
                "hiring_recommendation": parsed.get("hiring_recommendation", default_rec),
                "strengths_summary":     parsed.get("strengths_summary", ""),
                "weaknesses_summary":    parsed.get("weaknesses_summary", ""),
                "roadmap":               parsed.get("roadmap", []),
                "suggestion":            parsed.get("suggestion", ""),
            }
    except Exception as e:
        logging.error(f"generate_final_report_phase2 error: {e}")

    return {
        "overall_score": raw_overall, "comm_score": raw_comm,
        "tech_score": raw_tech, "conf_score": raw_conf, "problem_score": raw_prob,
        "hiring_recommendation": default_rec,
        "strengths_summary": "Report generation failed — see individual scores.",
        "weaknesses_summary": "Report generation failed — see individual scores.",
        "roadmap": [], "suggestion": ""
    }


def text_to_speech(text: str) -> bytes | None:
    """
    Convert text to speech using the NVIDIA / OpenAI TTS endpoint.
    Returns raw MP3 bytes on success, or None if TTS is unavailable.
    Falls back gracefully so the interview can still run text-only.
    """
    try:
        response = client.audio.speech.create(
            model="eleven-labs/eleven-flash-v2-5",   # NVIDIA-hosted Eleven Labs
            voice="Rachel",
            input=text[:4096],
        )
        return response.content
    except Exception as primary_err:
        logging.warning(f"Primary TTS failed ({primary_err}), trying openai/tts-1...")
        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice="nova",
                input=text[:4096],
            )
            return response.content
        except Exception as fallback_err:
            logging.error(f"TTS fully unavailable: {fallback_err}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — AI Interviewer Logic
# ─────────────────────────────────────────────────────────────────────────────

def generate_greeting(candidate_name: str, role: str) -> str:
    """
    Build a personalised opening greeting from session data — no LLM call needed.
    Spoken via SpeechSynthesis at the very start of the room.
    """
    first_name = (candidate_name or "there").strip().split()[0]
    return (
        f"Hello {first_name}, welcome to your {role} interview. "
        f"I'm your AI interviewer today. "
        f"I'll be asking you a mix of HR, technical, behavioural, and situational questions. "
        f"Speak clearly and take your time. Let's get started!"
    )


def plan_interview_questions(role: str, resume_text: str) -> list:
    """
    Generate a structured 10-question interview plan for a session:
      HR (2) + Technical (5) + Behavioural (2) + Situational (1)
    Returns a list of dicts: [{type, topic_hint}, ...]
    The plan dictates *what type* to ask; actual question text is generated live
    by interviewer_turn() so context from previous answers is always included.
    """
    resume_snippet = (resume_text or "")[:2500].strip()
    prompt = f"""You are planning a job interview for the role: "{role}".

Candidate resume excerpt:
{resume_snippet if resume_snippet else "(no resume provided)"}

Generate a structured interview plan with EXACTLY 10 questions in this fixed order:
  [0] hr
  [1] hr
  [2] technical
  [3] behavioural
  [4] technical
  [5] technical
  [6] situational
  [7] technical
  [8] behavioural
  [9] technical

For each entry, provide a short topic_hint (5–10 words) that tells the interviewer what area to cover.
Base technical questions on the candidate's actual resume skills and the target role.
Return ONLY valid JSON — no markdown, no extra text:
{{
  "questions": [
    {{"type": "hr",          "topic_hint": "..."}},
    {{"type": "hr",          "topic_hint": "..."}},
    {{"type": "technical",   "topic_hint": "..."}},
    {{"type": "behavioural", "topic_hint": "..."}},
    {{"type": "technical",   "topic_hint": "..."}},
    {{"type": "technical",   "topic_hint": "..."}},
    {{"type": "situational", "topic_hint": "..."}},
    {{"type": "technical",   "topic_hint": "..."}},
    {{"type": "behavioural", "topic_hint": "..."}},
    {{"type": "technical",   "topic_hint": "..."}}
  ]
}}
"""
    try:
        resp = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[
                {"role": "system", "content": "You are a JSON-only API. Return exactly one JSON object."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.4,
            max_tokens=900,
        )
        parsed = extract_and_parse_json(resp.choices[0].message.content)
        if parsed and isinstance(parsed.get("questions"), list) and len(parsed["questions"]) == 10:
            return parsed["questions"]
    except Exception as e:
        logging.error(f"plan_interview_questions error: {e}")

    # Deterministic fallback plan
    return [
        {"type": "hr",          "topic_hint": "Self introduction and career background"},
        {"type": "hr",          "topic_hint": "Career goals and motivation for this role"},
        {"type": "technical",   "topic_hint": "Core technical skills listed on resume"},
        {"type": "behavioural", "topic_hint": "Overcoming a challenging team situation"},
        {"type": "technical",   "topic_hint": "System design or architecture relevant to role"},
        {"type": "technical",   "topic_hint": "Specific framework or tool from resume"},
        {"type": "situational", "topic_hint": "Managing a high-pressure deadline scenario"},
        {"type": "technical",   "topic_hint": "Debugging, optimisation, or code quality"},
        {"type": "behavioural", "topic_hint": "Leadership, ownership, or initiative example"},
        {"type": "technical",   "topic_hint": "Advanced or emerging topic for the role"},
    ]


def interviewer_turn(
    chat_history:  list,
    question_plan: list,
    current_q_idx: int,
    answer_text:   str,
    role:          str,
    is_follow_up:  bool = False,
) -> dict:
    """
    The core Phase 4 function — one GPT call per turn that:
      1. Sends the FULL conversation thread (persistent context)
      2. Evaluates the candidate's latest answer on 4 dimensions (0–10)
      3. Enforces the follow-up rule: avg < 6 → follow-up; avg ≥ 6 → next planned question
      4. Generates the next question text
      5. Returns updated chat history with answer + next question appended

    Args:
      chat_history:  persistent list of {role, content} messages (stored in DB)
      question_plan: list of {type, topic_hint} from plan_interview_questions()
      current_q_idx: 0-based index of the question currently being answered
      answer_text:   candidate's transcript for the current question
      role:          target role string
      is_follow_up:  True when this answer is responding to a follow-up question

    Returns dict with keys:
      comm_score, tech_score, conf_score, problem_score, overall_score  (0–10 float)
      strengths, weaknesses                                              (lists of str)
      follow_up_needed                                                   (bool)
      follow_up_reason                                                   (str)
      next_question                                                      (str)
      next_question_type                                                 (str)
      advance_idx                                                        (bool — True = move to next plan entry)
      updated_history                                                    (new chat_history with answer + Q appended)
    """
    # Determine which plan entry drives the NEXT question
    # If this was a follow-up, stay on the same plan entry
    advance   = not is_follow_up
    next_idx  = (current_q_idx + 1) if advance else current_q_idx
    if next_idx < len(question_plan):
        next_type  = question_plan[next_idx].get("type",       "technical")
        next_topic = question_plan[next_idx].get("topic_hint", "")
    else:
        next_type, next_topic = "technical", "a closing topic"

    # ── Build messages for this turn ─────────────────────────────
    # Add candidate's answer to history (for context)
    history_with_answer = chat_history + [
        {"role": "user", "content": answer_text}
    ]

    # Ephemeral evaluation prompt — appended as the last user turn,
    # NOT persisted in the stored chat_history
    eval_prompt = f"""[INTERVIEWER EVALUATION — respond with JSON only]

You just received the candidate's answer (above). Evaluate it strictly and honestly.

SCORING (0.0–10.0 per dimension; 10 = exceptional, 5 = average):
  - comm_score:    clarity, structure, articulation
  - tech_score:    technical accuracy, depth, specificity
  - conf_score:    decisiveness, no excessive hedging, conviction
  - problem_score: logical reasoning, structured approach

FOLLOW-UP RULE (mandatory):
  - Compute: overall = (comm + tech + conf + problem) / 4
  - If overall < 6.0 → follow_up_needed = true, write a targeted follow-up probing the weak area
  - If overall ≥ 6.0 → follow_up_needed = false, generate the next planned question

NEXT QUESTION (if NOT follow-up):
  type  : {next_type}
  topic : {next_topic}
  Rules : highly specific to the candidate's resume & prior answers; no generic questions

Return ONLY valid JSON — no markdown, no extra text:
{{
  "comm_score":       7.5,
  "tech_score":       6.0,
  "conf_score":       8.0,
  "problem_score":    7.0,
  "strengths":        ["Clear real-world example", "Structured STAR format"],
  "weaknesses":       ["Could have added more technical depth"],
  "follow_up_needed": false,
  "follow_up_reason": "",
  "next_question":    "Full question text here?",
  "next_question_type": "{next_type}"
}}
"""

    messages_to_send = history_with_answer + [
        {"role": "user", "content": eval_prompt}
    ]

    try:
        resp = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=messages_to_send,
            temperature=0.25,
            max_tokens=750,
        )
        parsed = extract_and_parse_json(resp.choices[0].message.content)

        if parsed and "next_question" in parsed:
            # Clamp every score to [0, 10]
            for key in ("comm_score", "tech_score", "conf_score", "problem_score"):
                parsed[key] = max(0.0, min(10.0, float(parsed.get(key, 5))))

            avg = (parsed["comm_score"] + parsed["tech_score"] +
                   parsed["conf_score"] + parsed["problem_score"]) / 4
            parsed["overall_score"] = round(avg, 2)

            # Hard-enforce the score < 6 follow-up rule
            if avg < 6.0:
                parsed["follow_up_needed"] = True

            # Build persistent history: answer + AI next question
            next_q_text = parsed["next_question"]
            updated_history = history_with_answer + [
                {"role": "assistant", "content": next_q_text}
            ]
            parsed["updated_history"] = updated_history
            parsed["advance_idx"]     = (not parsed["follow_up_needed"]) and advance

            return parsed

    except Exception as e:
        logging.error(f"interviewer_turn error: {e}")

    # Fallback — keep the session alive with a safe default
    fallback_q = "Could you elaborate on that with a specific example from your experience?"
    fallback_hist = history_with_answer + [{"role": "assistant", "content": fallback_q}]
    return {
        "comm_score": 5.0, "tech_score": 5.0, "conf_score": 5.0, "problem_score": 5.0,
        "overall_score":    5.0,
        "strengths":        [],
        "weaknesses":       ["Evaluation unavailable — technical error"],
        "follow_up_needed": False,
        "follow_up_reason": "",
        "next_question":     fallback_q,
        "next_question_type": next_type,
        "advance_idx":       advance,
        "updated_history":   fallback_hist,
    }