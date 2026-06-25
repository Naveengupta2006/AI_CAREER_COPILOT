import sys
import os

try:
    from reportlab.pdfgen import canvas
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "reportlab"])
    from reportlab.pdfgen import canvas

def create_pdf(filename):
    c = canvas.Canvas(filename)
    c.drawString(100, 750, "Resume of John Doe")
    c.drawString(100, 730, "Email: johndoe@example.com")
    c.drawString(100, 710, "Target: Software Engineer")
    c.drawString(100, 680, "Skills: Python, Flask, PostgreSQL, React, JavaScript, AWS")
    c.drawString(100, 650, "Experience:")
    c.drawString(100, 630, "- Senior Developer at Acme Corp (2023-Present)")
    c.drawString(120, 615, "Developed scalable Flask APIs and integrated third-party LLM endpoints.")
    c.drawString(120, 600, "Used PostgreSQL for high-throughput transactional database management.")
    c.drawString(100, 570, "- Software Engineer at Beta LLC (2021-2023)")
    c.drawString(120, 555, "Maintained React-based web dashboard interfaces and automated CI/CD deployment.")
    c.drawString(100, 520, "Projects:")
    c.drawString(100, 500, "- AI Interview Platform: Built with Python, Web Speech API, and OpenAI.")
    c.save()
    print(f"PDF successfully created: {filename}")

if __name__ == "__main__":
    pdf_path = os.path.join(os.path.dirname(__file__), "dummy_resume.pdf")
    create_pdf(pdf_path)
