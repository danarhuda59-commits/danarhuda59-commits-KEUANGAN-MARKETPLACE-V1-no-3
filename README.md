# Keuangan-1 — Aplikasi Keuangan & HPP Produk UMKM

FastAPI (Python 3.11) + MongoDB + React (CRA/CRACO, Tailwind, shadcn/ui).

Alur: Bahan → Supplier → Pembelian → Stok → Resep/BOM → Produksi (snapshot HPP) → Penjualan (HPP & laba) → Kas → Laporan.

## Menjalankan lokal

Prasyarat: Python 3.11, Node 20 (`.nvmrc`), yarn 1.22, MongoDB lokal.

```bash
# Backend
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock        # atau requirements.txt untuk resolve ulang
cp .env.example .env                    # isi MONGO_URL, DB_NAME, JWT_SECRET, ADMIN_*
uvicorn server:app --reload --port 8001 # http://localhost:8001/api/

# Frontend
cd frontend
yarn install --frozen-lockfile
cp .env.example .env                    # REACT_APP_BACKEND_URL=http://localhost:8001
yarn start                              # http://localhost:3000
```

Login pertama memakai `ADMIN_EMAIL` / `ADMIN_PASSWORD` dari `backend/.env` (di-seed otomatis saat backend start).

Test unit HPP: `cd backend && pytest tests/test_hpp.py -n 0`.

## Deploy

- **Frontend → Vercel**: root `frontend`, build `yarn build`, output `build`, env `REACT_APP_BACKEND_URL`. Konfigurasi di `frontend/vercel.json`.
- **Backend → Railway/Render/Fly**: root `backend`, pakai `Dockerfile`. Env: `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `CORS_ORIGINS`.
- **Database → MongoDB Atlas**: user `readWrite`, IP allowlist ke host backend.

Detail temuan keamanan, akurasi HPP, dan checklist deploy: lihat [`AUDIT.md`](AUDIT.md).
