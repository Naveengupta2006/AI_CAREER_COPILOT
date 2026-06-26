import sys
import os
from reportlab.pdfgen import canvas

def create_tricky_pdf(filename, name_x):
    c = canvas.Canvas(filename)
    # Draw email
    c.drawString(100, 700, "ritikgupta8130@gmail.com")
    # Draw name closer
    c.drawString(name_x, 700, "Ritik Gupta")
    
    # Draw website
    c.drawString(100, 680, "Social Media Marketing")
    c.drawString(name_x, 680, "Portfolio: http://bit.ly/4vJptQz")
    
    c.save()

import PyPDF2
import pypdf

for x in [220, 230, 240]:
    pdf_path = f"scratch/tricky_resume_{x}.pdf"
    create_tricky_pdf(pdf_path, x)
    
    print(f"\n--- Testing name_x = {x} ---")
    reader2 = PyPDF2.PdfReader(pdf_path)
    text2 = "".join(page.extract_text() or "" for page in reader2.pages)
    print("PyPDF2:", repr(text2.strip()))
    
    reader_pypdf = pypdf.PdfReader(pdf_path)
    text_pypdf = "".join(page.extract_text() or "" for page in reader_pypdf.pages)
    print("pypdf :", repr(text_pypdf.strip()))

    try:
        text_layout = "".join(page.extract_text(extraction_mode="layout") or "" for page in reader_pypdf.pages)
        print("pypdf layout:", repr(text_layout.strip()))
    except Exception as e:
        print("pypdf layout error:", e)
