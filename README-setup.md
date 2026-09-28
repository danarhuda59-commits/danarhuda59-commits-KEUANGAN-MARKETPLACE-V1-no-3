# README-setup — Import & Setup Keuangan-V1 (workspace baru)

Sumber: `github.com/danarhuda59-commits/Keuangan-V1` · branch default **`main`** (diverifikasi: `origin/HEAD -> origin/main`) · HEAD `0af3f67` · 7 commit, histori utuh (`git log`).

## Versi runtime (dari bukti di repo, bukan tebakan)

| Komponen | Bukti di repo | Versi | Workspace |
|---|---|---|---|
| Node | `frontend/.nvmrc` = `20`; `package.json` → `packageManager: yarn@1.22.22` | Node 20 / yarn 1.22 | Node 20.20.2, yarn 1.22.22 ✅ |
| Python | `backend/.python-version` = `3.11`; `backend/runtime.txt` = `python-3.11`; `Dockerfile` = `python:3.11-slim` | 3.11 | Python 3.11.16 ✅ |

Tidak ada `engines` di `package.json` (tidak kritikal karena `.nvmrc` ada).

## Hasil install dependency

### Frontend
- **Temuan**: `frontend/yarn.lock` **tidak ada di repo** (AUDIT.md lama mengklaim sudah dibuat, tetapi tidak pernah ter-commit). `yarn install --frozen-lockfile` **tidak mungkin dijalankan** pada clone bersih → dependensi di-resolve ulang dari `package.json` (semua versi utama sudah dipin eksak, hanya `jspdf`, `jspdf-autotable`, `xlsx` yang memakai `^`).
- `yarn install` sukses (74 s) → `frontend/yarn.lock` **baru dibuat, wajib di-commit** supaya build Vercel reproducible. Setelah itu `yarn install --frozen-lockfile` → "Already up-to-date" ✅.
- Warning yang tercatat (tidak di-upgrade, sesuai scope):
  - `Resolution field "qs@6.15.2" is incompatible with requested version "qs@~6.16.0"` dan `js-yaml@4.3.0` vs `^4.3.2` — resolutions di `package.json` mengunci versi lebih rendah dari yang diminta transitive dep. Tidak memblokir build.
  - `workbox-*@6.6.1` deprecated (transitive dari `react-scripts@5.0.1`), `svgo@2.8.1`, `stable@0.1.8` deprecated — bawaan CRA 5, tidak bisa diubah tanpa migrasi bundler.
  - `@emergentbase/overlay` & `@emergentbase/visual-edits` di `devDependencies` berupa tarball URL `assets.emergent.sh` — bila URL mati, `yarn install` di Vercel gagal (P2, lihat AUDIT.md).
- `CI=true yarn build` → lihat bagian Smoke test.

### Backend
- `requirements.txt` sudah **dipin penuh** (19 paket, `==`). Install ke venv workspace sukses tanpa error.
- **Temuan**: `backend/requirements.lock` **tidak ada di repo** padahal `Dockerfile` lama memakainya → `docker build` di clone bersih **akan gagal** (`COPY requirements.lock` tidak ditemukan). Sekarang dibuat dari venv bersih Python 3.11 (`pip freeze`, 42 paket) → **wajib di-commit**.
- Tidak ada paket yang gagal build (bcrypt 4.1.3, pydantic-core, numpy 2.4.6, pandas 3.0.6 wheel tersedia untuk 3.11).
- Peringatan: `requirements.emergent-image.txt` (128 baris, berisi `litellm` URL privat + `emergentintegrations`) hanya referensi — **jangan** dipakai untuk install.

## Environment variables (hasil grep `os.environ` / `process.env`)

Backend (`backend/.env.example`):

| Var | Wajib | Dibaca di |
|---|---|---|
| `MONGO_URL` | ya (crash saat import bila kosong) | `core.py:8` |
| `DB_NAME` | ya | `core.py:9` |
| `JWT_SECRET` | ya (login 500 bila kosong) | `core.py:71,76` |
| `CORS_ORIGINS` | ya (KeyError saat start bila kosong; dipisah koma) | `server.py` |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | opsional — seed 1 owner saat startup | `server.py` startup |
| `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT`, `S3_REGION` | opsional — upload foto; tanpa ini `POST /upload` → 503 | `storage.py` |
| `PORT` | hanya Docker/PaaS | `Dockerfile` |

Frontend (`frontend/.env.example`): hanya `REACT_APP_BACKEND_URL` (tanpa `/api`, tanpa trailing slash). `NODE_ENV`, `DISABLE_EMERGENT_OVERLAY`, `ENABLE_HEALTH_CHECK` hanya dibaca `craco.config.js`/plugin dev — tidak dibutuhkan di production.

**Hardcode URL**: tidak ada `localhost:8000/8001` di `frontend/src/` — semua lewat `src/lib/api.js` → `process.env.REACT_APP_BACKEND_URL`.

## Audit credential ter-commit
- `git log --all -p` di-grep untuk `JWT_SECRET=`, `mongodb+srv://` dengan password, `AKIA…`, `ghp_`/`github_pat_`, file `.env` → **tidak ada** credential asli di HEAD maupun histori. Hanya placeholder dokumentasi.
- Password demo lama `admin123` (akun `danarhuda59@gmail.com`) ada di `backend/tests/backend_test.py` & `test_iteration2.py` — test saja, bukan runtime; akun ini tidak di-seed di sini. Bila akun itu pernah dipakai di DB produksi, **ganti passwordnya**.
- PAT GitHub yang pernah ditempel di chat: **revoke** (GitHub → Settings → Developer settings → Fine-grained tokens). Repo terbukti public; tidak ada token yang dipakai untuk clone.

## Akun admin baru
- Di-seed saat backend start dari `ADMIN_EMAIL`/`ADMIN_PASSWORD` (`server.py`), **atau** manual tanpa restart: `cd backend && python scripts/create_admin.py` (idempotent; opsional `ADMIN_NAME`, `ADMIN_BUSINESS_NAME`). Tidak ada password hardcode.
- Kredensial dev tersimpan di `backend/.env` (di-gitignore) dan `memory/test_credentials.md` (di-gitignore).

## Menjalankan lokal

```bash
# Backend
cd backend && python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env            # isi MONGO_URL, DB_NAME, JWT_SECRET, CORS_ORIGINS, ADMIN_*
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
# → GET http://localhost:8001/api/health  {"status":"ok","database":"ok"}

# Frontend
cd frontend && yarn install --frozen-lockfile
cp .env.example .env            # REACT_APP_BACKEND_URL=http://localhost:8001
yarn start                      # http://localhost:3000/login
```

Test unit: `cd backend && pytest tests/test_hpp.py tests/test_target_margin.py -n 0` → 16 passed.

## Docker (backend)
`backend/Dockerfile` ditulis ulang: multi-stage (builder venv → `python:3.11-slim`), user non-root `app`, `uvicorn --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` (rate-limit login membaca IP asli di balik proxy Railway/Render/Fly), `HEALTHCHECK` ke `/api/health`.

```bash
cd backend && docker build -t keuangan-backend . && \
docker run --rm -p 8000:8000 --env-file .env -e PORT=8000 keuangan-backend
curl localhost:8000/api/health
```

> **Belum diverifikasi di workspace ini**: tidak ada Docker daemon/CLI di container (`which docker` kosong, tidak ada `/var/run/docker.sock`). Jalankan perintah di atas di mesin Anda / CI sebelum deploy.

## Deploy
- **Frontend → Vercel**: root `frontend`, build `yarn build`, output `build`, env `REACT_APP_BACKEND_URL=https://<backend>`; SPA rewrite di `frontend/vercel.json`.
- **Backend → Railway/Render/Fly**: root `backend`, Dockerfile; env wajib `MONGO_URL` (Atlas), `DB_NAME`, `JWT_SECRET` (≥32 byte acak), `CORS_ORIGINS=https://<app>.vercel.app` (tanpa `*` — dengan `allow_credentials=True`, browser menolak `*`), opsional `ADMIN_EMAIL/ADMIN_PASSWORD` untuk seed pertama (hapus setelah login), `S3_*` untuk upload foto.
- **CORS Vercel ↔ backend**: dicek di `server.py` — origin dibaca dari `CORS_ORIGINS` (dipisah koma), cookie `SameSite=None; Secure` + header `Authorization: Bearer` dari `localStorage` → login lintas-domain berjalan tanpa bergantung cookie.
- Health check PaaS: `GET /api/health` (ping Mongo; 503 bila DB tidak terjangkau).

## Smoke test (workspace ini)
| Cek | Hasil |
|---|---|
| `GET /api/health` | `{"status":"ok","database":"ok"}` ✅ |
| `GET /api/` | 200 ✅ |
| `POST /api/auth/login` admin baru | 200 + token ✅ |
| Halaman `/login` render, login → `/` Dashboard | ✅ (screenshot) |
| `pytest tests/test_hpp.py tests/test_target_margin.py -n 0` | 16 passed ✅ |
| `CI=true yarn build` | lolos (30 s), 0 referensi `emergentbase` di bundle ✅ |
| `docker build` | ⛔ tidak bisa dijalankan di workspace (tanpa Docker) |

## Perubahan yang dilakukan (hanya setup, tanpa refactor fitur)
| File | Aksi |
|---|---|
| `frontend/yarn.lock` | baru (hasil `yarn install`) |
| `backend/requirements.lock` | baru (`pip freeze` venv bersih 3.11) |
| `backend/.env.example`, `frontend/.env.example` | baru (variabel yang benar-benar dibaca kode) |
| `backend/Dockerfile` | ditulis ulang: multi-stage, non-root, PORT env, proxy-headers, healthcheck |
| `backend/.dockerignore` | tambah `.git`, `.pytest_cache`, `requirements.emergent-image.txt` |
| `backend/server.py` | tambah `GET /api/health` (ping Mongo) — satu endpoint, tidak menyentuh logika lain |
| `backend/scripts/create_admin.py` | baru — buat owner dari env |
| `README-setup.md`, `AUDIT.md` (Fase 5 gap analysis), `memory/PRD.md` | dokumentasi |
| Kode fitur (`routers/*`, `core.py`, `frontend/src/**`) | **tidak diubah** |
