import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pypdf

pdf_path = os.path.join(os.path.dirname(__file__), "dummy_resume.pdf")

reader = pypdf.PdfReader(pdf_path)
page = reader.pages[0]

try:
    text_layout = page.extract_text(extraction_mode="layout")
    print("Supports layout extraction mode:")
    print(repr(text_layout[:300]))
except Exception as e:
    print(f"Error with layout mode: {e}")
