from openai import OpenAI
import json

client = OpenAI()

def analyze_resume(resume_text, user_goal):
    prompt = f"""
    
you are a senior software engineer and hiring manager.

evaluate the resume based on the user's goal.

user goal: "{user_goal}"

STRICT RULES:
- Extractonly relevant skills for this goal
- remove irrelevant tools [excel for backend, etc]
- identify real gaps
- generate roadmap only for missing fields
- make output DIFFERENT based on goal

return only JSON:
{{
"skills": [],
"missing_skills": [],
"roadmap": [],
"interview_prep": []
}}
Resume:
{resume_text}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()

        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        start = content.find("{")
        end = content.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError("Could not find JSON object in response")

        return json.loads(content[start:end])
    
    except Exception as e:
        return {
            "skills": [],
            "missing_skills": [],
            "roadmap": [],
            "interview_prep": [],
            "error": str(e)
        }
