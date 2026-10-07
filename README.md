# ✂️ YouTube Clipper (Short-Form Auto Clipper)

Aplikasi web lokal full-stack untuk memotong video panjang (YouTube maupun file video lokal) menjadi video vertikal 9:16 untuk YouTube Shorts, TikTok, dan Instagram Reels secara otomatis dan presisi.

---

## 🚀 Fitur Utama

- **Fase 0: Portable & Standalone Setup**
  - Menggunakan portable FFmpeg (dengan dukungan hardware acceleration AMD AMF `h264_amf` dan software `libx264`).
  - Backend FastAPI + Frontend React (Vite, TailwindCSS, Lucide-style UI).
- **Fase 1: Manual Clipping & Real-time Progress**
  - Download video YouTube via `yt-dlp` lengkap dengan metadata, chapters, dan YouTube Heatmap ("Most Replayed").
  - Player interaktif dengan kontrol keyboard (I / O / Space / Seek frame / Enter).
  - Background task worker dengan WebSocket real-time progress.
- **Fase 2: Auto Transcription & Animated Captions**
  - Integrasi `faster-whisper` untuk transkripsi lokal dengan timestamp per-kata (*word-level timestamps*).
  - Panel transkrip interaktif: klik untuk lompat video, Shift+klik untuk langsung buat klip.
  - Burn-in subtitle ASS profesional dengan 3 preset: *Bold Highlight*, *Boxed*, dan *Minimalist*, serta opsi export file SRT.
- **Fase 3: AI Highlight Detection (Auto-Clip)**
  - Dual Provider: **Ollama (Local CPU/GPU)** atau **Cloud API (Gemini / OpenAI-compatible)**.
  - Menganalisa segmen transkrip dipadukan dengan YouTube Heatmap score.
  - Memotong otomatis klip yang memiliki *storytelling* lengkap dan viral-worthy dengan snap ke batas kalimat terdekat.
- **Fase 4: Vertical Reframe & Face Tracking (9:16)**
  - MediaPipe Face Detection untuk mendeteksi posisi pembicara.
  - Algoritma Exponential Moving Average (EMA) smoothing untuk pergerakan kamera halus.
  - Scene-cut snapping saat ada pergantian sudut kamera.
  - Pilihan mode: *Blur Background*, *Face Tracking*, dan *Manual Center Crop*.
- **Fase 5: Polish & Workflow Enhancements**
  - Import file video lokal langsung dari disk tanpa download YouTube.
  - Generator judul, deskripsi, dan hashtag otomatis berbasis AI LLM untuk setiap klip.
  - Preset konfigurasi & Halaman Pengaturan (Settings) terpadu.

---

## 🛠️ Prasyarat (Prerequisites)

1. **Python 3.10 - 3.12** terinstal di Windows.
2. **Node.js** (v18+) terinstal di Windows.
3. *(Opsional)* **Ollama** jika ingin menggunakan AI lokal (`ollama run qwen2.5:3b`).

---

## 🏃 Cara Menjalankan

Cukup jalankan script launcher:

```bat
start.bat
```

Script akan otomatis:
1. Mendownload build portable FFmpeg jika belum tersedia.
2. Membuat Python virtual environment (`.venv`) dan menginstall dependencies backend.
3. Menginstall dependencies frontend (`npm install`).
4. Menjalankan backend di `http://localhost:8000` dan frontend di `http://localhost:5173`.
5. Membuka browser secara otomatis.

---

## ⌨️ Shortcut Keyboard Editor

| Tombol | Fungsi |
|---|---|
| `Space` | Play / Pause video |
| `I` | Set IN point (titik awal klip) |
| `O` | Set OUT point (titik akhir klip) |
| `Enter` | Buat klip baru dari IN-OUT |
| `←` / `→` | Mundur / Maju 1 detik (Shift = 5 detik) |
| `,` / `.` | Mundur / Maju per frame |
| `Esc` | Reset titik IN dan OUT |
