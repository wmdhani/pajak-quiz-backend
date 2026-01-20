import os
import json
import random
import fitz  # PyMuPDF
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

# --- KONFIGURASI ---
app = FastAPI()

# Inisialisasi Client Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# CORS (Agar Frontend bisa akses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- FUNGSI PDF READER (PINDAHAN DARI PROCESSOR.PY) ---
def extract_random_context(pdf_path, num_pages=5):
    try:
        # Cek apakah file ada
        if not os.path.exists(pdf_path):
            print(f"Error: File PDF tidak ditemukan di {pdf_path}")
            return ""
            
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        # Ambil halaman secara acak
        num_pages = min(num_pages, total_pages)
        random_pages = random.sample(range(total_pages), num_pages)
        
        text_list = []
        for p in random_pages:
            # Bungkus str() untuk keamanan tipe data
            text = str(doc[p].get_text("text"))
            if text.strip():
                text_list.append(text)
                
        doc.close()
        return " ".join(text_list)
    except Exception as e:
        print(f"PDF Processing Error: {str(e)}")
        return ""

# --- ENDPOINT UTAMA ---
# Note: Kita pakai /api/ di depan agar sesuai dengan routing Vercel
@app.get("/api/generate-quiz/{jumlah}") 
async def generate_quiz(jumlah: int):
    try:
        # 1. Cari Lokasi PDF (Path Absolut - Wajib di Vercel)
        base_dir = os.path.dirname(os.path.realpath(__file__))
        pdf_path = os.path.join(base_dir, "materi.pdf") 

        # 2. Baca PDF
        context = extract_random_context(pdf_path, num_pages=3)
        
        # Fallback jika PDF gagal baca
        if not context:
            return {
                "status": "error", 
                "message": "Gagal membaca PDF. Pastikan file 'materi.pdf' ada di folder 'api'."
            }
            
        # 3. Kirim ke AI
        prompt = f"""
        Role: Ahli Pajak DJP.
        Tugas: Buat {jumlah} soal pilihan ganda (A-E) tingkat sulit dari materi ini.
        
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
        
        # 4. Bersihkan Respons JSON
        raw = chat.choices[0].message.content or ""
        clean = raw.replace("```json", "").replace("```", "").strip()
        
        # Ambil hanya bagian array [...] untuk membuang teks intro/outro
        if "[" in clean and "]" in clean:
            clean = clean[clean.find('['):clean.rfind(']')+1]
            
        return {"status": "success", "data": json.loads(clean)}

    except Exception as e:
        print(f"Server Error: {str(e)}")
        return {"status": "error", "message": str(e)}