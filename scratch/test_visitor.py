import pypdf

pdf_path = "scratch/tricky_resume_220.pdf"
reader = pypdf.PdfReader(pdf_path)
page = reader.pages[0]

extracted_parts = []
def visitor(text, cm, tm, font_dict, font_size):
    extracted_parts.append((text, tm, font_size))

page.extract_text(visitor_text=visitor)

for text, tm, size in extracted_parts[:20]:
    print(f"Text: {repr(text)}, TM: {tm}, Size: {size}")
