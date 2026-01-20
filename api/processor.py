import fitz  # PyMuPDF
import random

def extract_random_context(pdf_path, num_pages=5):
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        num_pages = min(num_pages, total_pages)
        random_pages = random.sample(range(total_pages), num_pages)
        
        text_list = []
        for p in random_pages:
            text = str(doc[p].get_text("text"))
            if text.strip():
                text_list.append(text)
                
        doc.close()
        return " ".join(text_list)
    except Exception as e:
        print(f"PDF Error: {e}")
        return ""