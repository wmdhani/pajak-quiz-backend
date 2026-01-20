import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from processor import extract_random_context

# Inisialisasi
app = FastAPI()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/generate-quiz/{jumlah}")
async def generate_quiz(jumlah: int):
    try:
        # FIX VERCEL: Gunakan path absolut agar PDF selalu ketemu
        base_dir = os.path.dirname(os.path.realpath(__file__))
        pdf_path = os.path.join(base_dir, "materi.pdf") # Pastikan nama file PDF Anda 'materi.pdf'

        context = extract_random_context(pdf_path, num_pages=3)
        if not context:
            return {"status": "error", "message": "Gagal membaca PDF."}
            
        prompt = f"""
        Role: Ahli Pajak DJP.
        Tugas: Buat {jumlah} soal pilihan ganda (A-E) sulit & menjebak dari materi ini.
        
        Materi: {context[:8000]}
        
        Output JSON Array Valid (Tanpa Markdown):
        [
          {{
            "question": "...",
            "options": ["A. x", "B. x", "C. x", "D. x", "E. x"],
            "answer": "A"
          }}
        ]
        """
        
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.5
        )
        
        # Bersihkan JSON
        raw = chat.choices[0].message.content or "" 
        
        clean = raw.replace("```json", "").replace("```", "").strip()
        if "[" in clean and "]" in clean:
            clean = clean[clean.find('['):clean.rfind(']')+1]
            
        return {"status": "success", "data": json.loads(clean)}

    except Exception as e:
        return {"status": "error", "message": str(e)}