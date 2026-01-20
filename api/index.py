import os
import json
import random
import asyncio
import math
import fitz  # PyMuPDF
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

# --- KONFIGURASI ---
app = FastAPI()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE TOPIK & KATA KUNCI ---
# Format: "Kode Topik": {"persen": X, "keywords": ["kata1", "kata2"]}
TOPICS = {
    "KUP": {"persen": 0.1333, "keywords": ["ketentuan umum", "KUP", "sanksi pajak", "keberatan", "banding"]},
    "PPh": {"persen": 0.1333, "keywords": ["pajak penghasilan", "PPh", "subjek pajak", "objek pajak", "PTKP"]},
    "PPN_PPnBM": {"persen": 0.1333, "keywords": ["pertambahan nilai", "PPN", "PPnBM", "faktur pajak", "pengusaha kena pajak"]},
    "TIK": {"persen": 0.1333, "keywords": ["teknologi informasi", "sistem informasi", "basis data", "aplikasi", "TIK"]},
    "PBB_P5L": {"persen": 0.0667, "keywords": ["PBB", "bumi dan bangunan", "P5L", "NJOP"]},
    "Bea_Meterai": {"persen": 0.0667, "keywords": ["bea meterai", "meterai", "dokumen terutang"]},
    "Organisasi": {"persen": 0.0667, "keywords": ["struktur organisasi", "tugas fungsi", "DJP", "kementerian keuangan"]},
    "Internalisasi": {"persen": 0.0667, "keywords": ["kode etik", "disiplin", "budaya kerja", "nilai kementerian"]},
    "Kepegawaian": {"persen": 0.0667, "keywords": ["ASN", "kepegawaian", "jabatan", "cuti", "pengembangan kompetensi"]},
    "Keuangan": {"persen": 0.0667, "keywords": ["pengelolaan keuangan", "DIPA", "anggaran", "perbendaharaan"]},
    "Tata_Naskah": {"persen": 0.0667, "keywords": ["tata naskah", "surat dinas", "arsip", "korespondensi"]}
}

# --- FUNGSI PENCARI KONTEKS CERDAS ---
def get_context_by_topic(doc, topic_key, num_pages=2):
    """Mencari halaman PDF yang mengandung kata kunci topik tertentu."""
    keywords = TOPICS[topic_key]["keywords"]
    matched_pages = []
    
    # Scan acak maksimal 50 halaman biar tidak berat, atau scan semua jika PDF kecil
    # Di Vercel kita harus efisien. Kita coba sampling acak dulu.
    total_pages = len(doc)
    scan_indices = random.sample(range(total_pages), min(50, total_pages))
    
    for p_idx in scan_indices:
        try:
            page_text = doc[p_idx].get_text("text").lower()
            # Cek apakah ada keyword topik di halaman ini
            if any(k.lower() in page_text for k in keywords):
                matched_pages.append(doc[p_idx].get_text("text"))
        except:
            continue
            
    if not matched_pages:
        # Fallback: Jika tidak ketemu keyword, ambil acak
        fallback_indices = random.sample(range(total_pages), min(num_pages, total_pages))
        return " ".join([doc[i].get_text("text") for i in fallback_indices])
    
    # Ambil sampel dari halaman yang cocok
    selected = random.sample(matched_pages, min(len(matched_pages), num_pages))
    return " ".join(selected)

# --- FUNGSI PEMBUAT SOAL (ASYNC) ---
async def generate_questions_for_topic(doc, topic, count):
    if count == 0: return []
    
    # 1. Cari konteks yang relevan dengan topik
    context = get_context_by_topic(doc, topic)
    if not context: return []

    # 2. Prompt Spesifik & Ketat
    prompt = f"""
    Bertindaklah sebagai Asesor Ukom DJP. Buat {count} soal pilihan ganda (A-E) TENTANG {topic}.
    
    MATERI ACUAN (HANYA GUNAKAN INI):
    {context[:6000]}
    
    ATURAN SANGAT PENTING:
    1. JANGAN HALUSINASI. Jika di materi tidak ada angka/studi kasus spesifik, JANGAN MENGARANG CONTOH KASUS. Buatlah soal konseptual/teori berdasarkan teks yang ada.
    2. Format Output wajib JSON Array murni.
    3. Tingkat kesulitan: Menengah-Sulit (HOTS).
    
    Contoh Output JSON:
    [
      {{
        "question": "Berdasarkan pasal...",
        "options": ["A. x", "B. x", "C. x", "D. x", "E. x"],
        "answer": "A"
      }}
    ]
    """
    
    try:
        # Panggil Groq secara Async
        response = await asyncio.to_thread(
            client.chat.completions.create,
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3 # Suhu rendah agar lebih patuh data
        )
        
        raw = response.choices[0].message.content or ""
        clean = raw.replace("```json", "").replace("```", "").strip()
        if "[" in clean and "]" in clean:
            clean = clean[clean.find('['):clean.rfind(']')+1]
            return json.loads(clean)
        return []
    except Exception as e:
        print(f"Error {topic}: {e}")
        return []

# --- ENDPOINT UTAMA ---
@app.get("/api/generate-quiz/{total_soal}")
async def generate_quiz(total_soal: int):
    try:
        base_dir = os.path.dirname(os.path.realpath(__file__))
        pdf_path = os.path.join(base_dir, "materi.pdf")
        
        if not os.path.exists(pdf_path):
            return {"status": "error", "message": "File materi.pdf tidak ditemukan"}

        doc = fitz.open(pdf_path)
        tasks = []
        
        # 1. Hitung alokasi soal per topik
        allocations = {}
        current_total = 0
        
        for topic, data in TOPICS.items():
            # Pembulatan ke bawah dulu
            n = math.floor(total_soal * data["persen"])
            allocations[topic] = n
            current_total += n
            
        # Jika ada sisa (karena pembulatan), tambahkan ke topik prioritas (KUP/PPh)
        sisa = total_soal - current_total
        prioritas = ["KUP", "PPh", "PPN_PPnBM", "TIK"]
        for i in range(sisa):
            t = prioritas[i % len(prioritas)]
            allocations[t] += 1
            
        # 2. Buat Task Paralel (Semua topik diproses bersamaan)
        for topic, count in allocations.items():
            if count > 0:
                tasks.append(generate_questions_for_topic(doc, topic, count))
                
        # 3. Eksekusi Paralel (Nunggu semua selesai)
        results = await asyncio.gather(*tasks)
        doc.close()
        
        # 4. Gabungkan Hasil
        final_quiz = []
        for res in results:
            final_quiz.extend(res)
            
        # Acak urutan soal biar tidak berkelompok per topik
        random.shuffle(final_quiz)
        
        # Potong jika kelebihan (jarang terjadi, tapi buat jaga-jaga)
        return {"status": "success", "data": final_quiz[:total_soal]}

    except Exception as e:
        print(f"Server Error: {str(e)}")
        return {"status": "error", "message": str(e)}