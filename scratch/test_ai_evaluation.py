import sys
import os

# Add the project root directory to the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ.get("NVIDIA_API_KEY")
)

def test_raw_evaluation():
    question = "Can you walk me through your experience with Flask APIs?"
    answer = "sdasd"
    target_role = "Software Engineer"
    
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
    
    print("Calling completions API...")
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
        content = response.choices[0].message.content
        print("Raw Completion Output:")
        print("---------------------")
        print(content)
        print("---------------------")
        
        # Test the parsing logic
        content_stripped = content.strip()
        if "```json" in content_stripped:
            content_stripped = content_stripped.split("```json")[1].split("```")[0].strip()
        elif "```" in content_stripped:
            content_stripped = content_stripped.split("```")[1].split("```")[0].strip()
            
        start = content_stripped.find("{")
        end = content_stripped.rfind("}") + 1
        if start == -1 or end == 0:
            print("Parsing Error: start or end index not found!")
            print(f"start: {start}, end: {end}")
        else:
            parsed = content_stripped[start:end]
            print("Found JSON substring:")
            print(parsed)
            import json
            try:
                data = json.loads(parsed)
                print("Successfully parsed JSON!")
                print(data)
            except Exception as parse_err:
                print(f"JSON Decoded Error: {parse_err}")
                
    except Exception as e:
        print(f"Completions Error: {e}")

if __name__ == "__main__":
    test_raw_evaluation()
