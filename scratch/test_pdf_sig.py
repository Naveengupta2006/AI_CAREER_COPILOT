import pypdf
import inspect

reader = pypdf.PdfReader("scratch/tricky_resume_220.pdf")
page = reader.pages[0]

sig = inspect.signature(page.extract_text)
print("Signature:", sig)
print("Docstring:", page.extract_text.__doc__[:1000])
