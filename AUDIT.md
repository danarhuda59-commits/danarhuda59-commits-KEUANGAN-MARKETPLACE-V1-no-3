# Laporan Audit — Keuangan-1 (Aplikasi Keuangan & HPP UMKM)

Tanggal: Juni 2026 · Lingkup: import repo, setup reproducible, audit **tanpa refactor**. Kode aplikasi tidak diubah kecuali yang tercatat di bagian "Perubahan yang dilakukan".

---

## Fase 0 — Akses & Keamanan

| Item | Hasil |
|---|---|
| Clone `main` | OK. HEAD `45f4131` ("Auto-generated changes"), 5 commit terakhir semua buatan Emergent. |
| Repo private? | Saat dicek, repo **bisa di-clone tanpa token** (public). Bila seharusnya private, cek visibilitas di GitHub → Settings → Danger Zone. |
| Credential ter-commit | **Tidak ada** `.env`, connection string, atau JWT secret hardcoded di `server.py`/`core.py`. Semua dibaca dari `os.environ`. |
| Password di repo | `admin123` ada di `backend/tests/backend_test.py` & `test_iteration2.py` (akun demo lama `danarhuda59@gmail.com`). Hanya test, bukan runtime. Akun ini **tidak** di-seed di setup baru. |
| **PAT** | Anda menempelkan PAT di percakapan sebelumnya → **revoke sekarang**: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Delete. Import sudah selesai, token tidak diperlukan lagi. |

## Fase 1 — Backend (FastAPI, Python 3.11)

**Temuan `requirements.txt` asli**: berisi 128 baris hasil `pip freeze` dari image Emergent, termasuk paket yang **tidak bisa di-install di luar Emergent**:
- `litellm @ https://customer-assets.emergentagent.com/...whl` (URL privat)
- `emergentintegrations==0.2.1` (bukan PyPI)
- ±90 paket tidak dipakai kode (google-genai, huggingface_hub, grpcio, boto3, dll.)

**Perubahan (minimal, dicatat)**:
- `requirements.txt` ditulis ulang hanya berisi paket yang benar-benar di-import (18 baris, versi **dipin sama persis** dengan freeze asli — tidak ada upgrade/downgrade). File asli disimpan sebagai `backend/requirements.emergent-image.txt` untuk referensi.
- `backend/requirements.lock` = `pip freeze` dari venv bersih Python 3.11 (38 paket). **Ini yang dipakai Dockerfile.**
- Tidak ada paket yang gagal build (bcrypt 4.1.3, pydantic-core 2.x OK di 3.11).

**Env var yang dibaca kode** (→ `backend/.env.example`):

| Var | Wajib | Catatan |
|---|---|---|
| `MONGO_URL` | ya | `core.py:8` — crash saat import jika kosong (fail-fast, bagus) |
| `DB_NAME` | ya | `core.py:9` |
| `JWT_SECRET` | ya | `core.py:71,76` — **tidak ada default**; login akan 500 bila kosong. Tidak ada di `.env` template Emergent → sudah ditambahkan |
| `CORS_ORIGINS` | tidak | default `*` (lihat temuan keamanan) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | tidak | seed admin saat startup (`server.py:43`) |
| `INTEGRATION_PROXY_URL`, `EMERGENT_LLM_KEY` | tidak | hanya untuk upload file/logo via Emergent Object Storage |

**Verifikasi**: `GET /api/` → 200, `POST /api/auth/login` admin → 200 + token, `pytest tests/test_hpp.py` → **11 passed**.

## Fase 2 — Frontend (React CRA + CRACO)

- `yarn install` (Node 20.20, yarn 1.22.22) → `frontend/yarn.lock` dibuat (`package.json` mengunci `packageManager: yarn@1.22.22`, sesuai pilihan Anda).
- **Audit `craco.config.js`** — tiga plugin Emergent, semuanya **sudah ter-gate** dan tidak masuk production build:

| Plugin | Gate | Status di `yarn build` |
|---|---|---|
| `@emergentbase/visual-edits` | `NODE_ENV !== "production"` + try/catch MODULE_NOT_FOUND | tidak dimuat |
| `@emergentbase/overlay` | `NODE_ENV !== "production"` && `DISABLE_EMERGENT_OVERLAY !== "true"` | tidak dimuat |
| `plugins/health-check/*` | `ENABLE_HEALTH_CHECK === "true"` | tidak dimuat |

  → **Tidak perlu diubah.** Bundle hasil build di-grep: 0 referensi `emergentbase`/`visual-edits`.
- **Yang masih ikut ke production** (dilaporkan, tidak diubah): `public/index.html` memuat `https://assets.emergent.sh/scripts/emergent-main.js` dan snippet PostHog (`api_host: https://ap.emergent.sh`). Ini telemetri Emergent, bukan fitur aplikasi. **Rekomendasi P1**: hapus 2 blok `<script>` tersebut sebelum go-live.
- `@emergentbase/*` di `devDependencies` berupa tarball URL `assets.emergent.sh`. Tidak di-import oleh `src/`. Dibiarkan karena craco menanganinya dengan try/catch; risiko: bila URL itu mati, `yarn install` di Vercel gagal → pindahkan ke `optionalDependencies` atau hapus (P2).
- Hardcoded URL: **tidak ada**. Semua panggilan lewat `src/lib/api.js` → `process.env.REACT_APP_BACKEND_URL` + `/api`. Cookie dikirim `withCredentials: true` **dan** token juga dikirim via header `Authorization: Bearer` dari `localStorage` → di Vercel (domain berbeda dari backend) login tetap jalan lewat header meski cookie `SameSite=None` bermasalah.
- `CI=true yarn build` → **lolos, 0 warning ESLint**. Aman untuk Vercel.

## Fase 3 — Verifikasi lokal

- MongoDB lokal → backend (supervisor, port 8001) → frontend dev server: login, master data, resep/HPP, transaksi, laporan diuji (lihat hasil testing agent di ringkasan).
- `pytest`: `test_hpp.py` 11 passed (pure unit). `backend_test.py` & `test_iteration2.py` adalah **test e2e yang bergantung URL preview** (`REACT_APP_BACKEND_URL` dari `/app/frontend/.env`, path absolut) dan akun demo lama `danarhuda59@gmail.com/admin123` → **dikategorikan "Emergent-preview-only", tidak diperbaiki** sesuai kesepakatan.
- `pytest.ini` memaksa `-n 2 --dist loadscope` (xdist). Untuk run serial: `pytest -n 0`.

## Fase 4 — Temuan Audit

### Keamanan

| # | Temuan | Tingkat | Lokasi |
|---|---|---|---|
| S1 | CORS default `*` **bersama** `allow_credentials=True`. Starlette akan mengirim `Access-Control-Allow-Origin: *` + credentials → browser menolak cookie cross-origin; secara efektif juga membuka API ke origin mana pun via Bearer token. Set `CORS_ORIGINS` ke domain Vercel eksplisit. | Tinggi | `server.py:27-33` |
| S2 | Token JWT diterima lewat **query string** `?auth=` (`current_user`) → token bocor ke access log/proxy/history browser. Dipakai untuk `<img src>` file logo. | Sedang | `core.py:99`, `lib/api.js:21` |
| S3 | Token disimpan di `localStorage` (XSS-readable) selain cookie httpOnly. | Sedang | `lib/api.js:8` |
| S4 | Rate limit login ada (5x/15 menit per IP+email, disimpan di Mongo) — bagus. Tapi `request.client.host` di belakang proxy (Railway/Render) = IP proxy → semua user berbagi satu bucket. Perlu `--proxy-headers` / `X-Forwarded-For`. Tidak ada rate limit di `/auth/register` (spam akun). | Sedang | `routers/auth.py:76-87` |
| S5 | Hash password: **bcrypt** langsung (`bcrypt.hashpw` + `gensalt`) — baik. `passlib` tidak dipakai. | OK | `core.py:58-66` |
| S6 | Tidak ada RBAC di router selain `settings_router` (owner-only untuk tambah/hapus user). Staff punya akses penuh ke transaksi, backup, restore, hapus demo. Isolasi per `business_id` konsisten via `Q(bid)`. | Sedang | semua router |
| S7 | `POST /restore` menghapus **semua** koleksi bisnis lalu insert dari file upload tanpa validasi skema → siapa pun dengan akun staff bisa memusnahkan data. | Tinggi | `settings_router.py:147-164` |
| S8 | Access token 24 jam, refresh 7 hari, tidak ada revocation/blacklist; ganti password tidak membatalkan token lama. | Rendah | `auth.py:56-60` |
| S9 | Upload logo bergantung **Emergent Object Storage** (`integrations.emergentagent.com` + `EMERGENT_LLM_KEY`). Di Railway/Render tanpa key → `init_storage` gagal (sudah terlihat di log startup: `Storage init failed: 400`). Fitur upload logo **tidak akan berfungsi** di production kecuali diganti (S3/Cloudinary/lokal). | Tinggi (fungsional) | `settings_router.py:15-28` |
| S10 | Seed admin `ADMIN_EMAIL` tidak divalidasi `EmailStr`, sedangkan login memvalidasi → email seperti `admin@x.local` bisa di-seed tapi **tidak bisa login**. | Rendah | `server.py:43-51` |
| S11 | `regex` lookup import memakai `re.escape` — aman dari ReDoS injeksi. Query Mongo memakai dict literal, tidak ada string interpolation → aman dari NoSQL injection. | OK | `settings_router.py:238` |

### Akurasi HPP

| # | Temuan | Tingkat |
|---|---|---|
| H1 | Semua perhitungan **float**, tidak ada `Decimal`. Pembulatan konsisten `round(x, 4)` di batch dan `round(x, 6)` di harga/unit. Untuk Rupiah (tanpa sen) error akumulasi < Rp0,01 per batch — **dapat diterima** untuk UMKM, tapi laporan Laba Rugi menjumlahkan ribuan transaksi float; rekomendasi jangka panjang: simpan dalam integer rupiah atau `Decimal`. | Sedang |
| H2 | Pembagian nol: `yield_qty = 0` → `hpp_per_unit = None` + `warning` (ditangani). `conversion_factor <= 0` → HTTP 400 (ditangani). `expand_items` sub-resep yield ≤ 0 → 400. Weighted average stok cek `(old+new) > 0`. **Baik.** | OK |
| H3 | Konversi satuan: 3 jalur — (a) unit == usage_unit, (b) unit == purchase_unit × `conversion_factor`, (c) tabel `unit_conversions` dua arah. Tidak ada konversi berantai (kg→gram→mg). Jika resep memakai satuan ketiga yang tidak ada di tabel → 400 dengan pesan jelas. **Baik.** | OK |
| H4 | `price_mode` default `"last"` (harga beli terakhir) untuk HPP resep, sedangkan produksi/HPP produk memakai `avg_price` (weighted average). Dua angka HPP berbeda untuk produk yang sama bisa membingungkan user — bukan bug, tapi perlu dijelaskan di UI. | Rendah |
| H5 | Waste dihitung `qty × (1 + waste%)` (markup atas kebutuhan), bukan `qty / (1 − waste%)` (yield-based). Keduanya valid, tapi hasil berbeda untuk waste besar (5% → selisih 0,26%). Konsisten di seluruh kode. | Info |
| H6 | `extra_costs` `pct_material` pada sub-resep di `expand_items` diteruskan sebagai `pct_material` terhadap **total bahan induk**, bukan bahan sub-resep saja → overhead % sub-resep bisa over-count saat produksi. | Sedang |
| H7 | Sub-resep dibatasi kedalaman 6 & self-reference dicek; siklus A→B→A terdeteksi via depth limit (pesan "melingkar") — cukup. | OK |
| H8 | Unit test HPP (`test_hpp.py`) mencakup kasus spesifikasi 6.400→9.900→990, waste, konversi, yield 0, input negatif → **11/11 lulus** di Python 3.11 bersih. | OK |

### Struktur kode

- Backend: `core.py` (337 baris) + 5 router. Tidak ada model Pydantic untuk dokumen Mongo (dict bebas, `{"_id":0}` projection) — konsisten tapi tanpa skema. `startup`/`shutdown` memakai `@app.on_event` (deprecated di FastAPI ≥0.93; masih jalan di 0.110).
- `to_list(100000)` / `to_list(200000)` di laporan & backup → semua data dimuat ke memori; OK untuk UMKM, perlu agregasi Mongo bila > 100k transaksi.
- Frontend: halaman besar (`Reports.jsx`, `Transactions.jsx`), state via SWR, tidak ada test. ESLint bersih.
- Kandidat pembersihan (bukan runtime): `memory/`, `test_reports/`, `.emergent/`, `design_guidelines.json`, `test_result.md`, `.gitconfig`, `frontend/plugins/health-check/`, `frontend/src/constants/testIds/` (dipakai test agent). Dibiarkan.

## Prioritas Perbaikan (tahap berikutnya)

**Sudah dikerjakan (iterasi 2)**
- ✅ S1 CORS: `CORS_ORIGINS` kini **wajib** (tanpa default `*`), daftar origin eksplisit.
- ✅ S9 Storage: upload foto memakai **S3-compatible (boto3)** via `backend/storage.py` — env `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT` (R2), `S3_REGION`. Tanpa env → `POST /upload` 503 dengan pesan jelas, `GET /meta.storage_enabled=false`, tombol upload di UI diganti pemberitahuan.
- ✅ Script telemetri Emergent (`emergent-main.js`, PostHog) dihapus dari `public/index.html`; title diganti.
- ✅ H6: `pct_material` pada sub-resep di `expand_items` kini dihitung dari biaya bahan sub-resep itu sendiri → HPP produksi == HPP resep.
- ✅ Fitur baru: **Target Margin Otomatis** — default usaha (`businesses.target_margin`, 30%) + override per resep (`recipes.target_margin`). Rumus `harga = HPP ÷ (1 − margin)`, dibulatkan ke atas Rp100; tampil di editor resep, Perhitungan HPP, dan kolom "Harga Saran" di tabel resep.

**P0 (sebelum go-live)**
1. Isi `S3_*` di env production (bucket R2/S3 privat, key `readWrite` bucket itu saja).
2. `CORS_ORIGINS=https://<app>.vercel.app` dan `JWT_SECRET` acak ≥ 32 byte di env production.

**P1**
5. Batasi `POST /restore`, `DELETE /demo`, `POST /users` ke role `owner` (S6, S7).
6. Hilangkan token di query string; ganti dengan signed URL berumur pendek untuk file (S2).
7. Rate limit berbasis `X-Forwarded-For` + rate limit `/auth/register` (S4).

**P2**
9. Migrasi nominal ke integer rupiah / `Decimal` (H1).
10. Migrasi `on_event` → lifespan; tambah model Pydantic untuk dokumen.
11. Pindahkan `@emergentbase/*` ke `optionalDependencies` atau hapus dari `package.json`.
12. Hapus test e2e yang bergantung URL preview atau parametrize `BASE` via env saja.

## Fase 5 — Kesiapan Deploy

**Frontend → Vercel** (`frontend/vercel.json` sudah dibuat)
- Root Directory: `frontend` · Install: otomatis `yarn install` (deteksi `yarn.lock`) · Build: `yarn build` · Output: `build`
- Env: `REACT_APP_BACKEND_URL=https://<backend-railway>.up.railway.app` (tanpa `/api`, tanpa trailing slash)
- SPA rewrite `/* → /index.html` sudah di `vercel.json`. Node 20 via `.nvmrc`.

**Backend → Railway / Render / Fly** (`backend/Dockerfile` sudah dibuat)
- Root Directory: `backend`. Image `python:3.11-slim`, install dari `requirements.lock`, `uvicorn server:app --host 0.0.0.0 --port $PORT`.
- Env wajib: `MONGO_URL` (Atlas SRV), `DB_NAME`, `JWT_SECRET`, `CORS_ORIGINS=https://<app>.vercel.app` (wajib, dipisah koma), `S3_BUCKET`/`S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_ENDPOINT` (R2: `https://<account>.r2.cloudflarestorage.com`, region `auto`), opsional `ADMIN_EMAIL`/`ADMIN_PASSWORD` untuk seed pertama (hapus setelah login pertama).
- Tambahkan `--proxy-headers --forwarded-allow-ips="*"` ke perintah uvicorn agar rate limit login membaca IP asli (S4).
- Health check path: `/api/`.

**MongoDB Atlas**
- Cluster M0/M2, Database User dengan role `readWrite` pada DB `DB_NAME` saja.
- Network Access: IP egress backend (Railway: aktifkan Static Outbound IP; Render: daftar IP di dashboard). Hindari `0.0.0.0/0`.
- `MONGO_URL=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority`.

## Fase 5 (re-import Keuangan-V1, Juni 2026) — Fitur yang ADA vs yang DIMINTA (Marketplace & Packaging)

Dasar plan pengembangan berikutnya. Kolom "Ada?" = kondisi kode HEAD `0af3f67`.

| Area diminta | Ada? | Yang sudah ada di kode | Gap |
|---|---|---|---|
| A. Channel Shopee/TikTok Shop/Tokopedia/Website | **Sebagian** | `db.channels` per bisnis, default seed 7 channel termasuk 4 itu (`auth.py:13`); `sales.channel` wajib (default `"Offline"`); CRUD via `master.py` | Sudah cukup; hanya perlu dipakai sebagai referensi (bukan free-text) |
| B. Data transaksi lengkap (Order ID, voucher, ongkir, subsidi ongkir, biaya iklan, refund, packaging, status pesanan, total dibayar/diterima) | **Sebagian kecil** | `sales`: `date, channel, customer, items[product,sku,qty,price,discount,hpp]`, `discount`, `platform_fee`, `service_fee`, `other_fee`, `net_total`, `total_hpp`, `profit`, `payment_method` | Tidak ada: `order_id`, harga normal, voucher, ongkir & subsidi, biaya admin/transaksi/iklan terpisah, refund/retur, biaya packaging, gross/net profit terpisah, margin, total dibayar customer vs diterima seller, **status pesanan** (sekarang semua penjualan dianggap selesai) |
| C. Rumus profit berlapis (Omzet Kotor → Bersih → Gross → Net → Margin) | **Sebagian** | `profit = net_total − total_hpp`; `safe_div` ada di `core.py`; `num()` menolak NaN/Inf | Belum ada pemisahan gross/net profit, margin per order, komponen biaya terpisah |
| D. Biaya Beban Packaging (modul + konfigurasi per produk) | **Tidak ada** sebagai modul | Hanya `extra_costs` tipe `packaging` di **resep** (masuk ke HPP batch) | Perlu koleksi `packaging_items` + `packaging_costs` per SKU; **risiko double counting**: jika resep sudah punya biaya `packaging`, transaksi tidak boleh menambah lagi → perlu aturan eksplisit |
| E. Import CSV/Excel marketplace (preview → mapping → validasi → duplikasi → konfirmasi) | **Sebagian** | `settings_router.py`: `/import/preview` & `/import/commit` untuk `sales` dengan kolom tetap `tanggal,channel,produk,qty,harga,diskon,biaya_platform` (CSV+XLSX via pandas/openpyxl), error per baris | Tidak ada mapping kolom bebas, tidak ada deteksi duplikat Order ID, tidak ada format per-marketplace |
| F. Rekonsiliasi marketplace | **Tidak ada** | — | Modul baru |
| G. Settlement/Payout | **Tidak ada** | — | Modul baru; `cash_transactions` bisa dipakai untuk mencatat uang masuk saat payout |
| H. Pengaturan biaya channel (persentase/nominal, periode berlaku) | **Tidak ada** | `platform_fee`/`service_fee` diinput manual per transaksi | Koleksi `sales_fees` + kalkulasi otomatis saat input/import |
| I. Dashboard filter channel/produk/SKU/status + KPI lengkap | **Sebagian** | `/dashboard` (omzet, laba, kas, stok), `/dashboard/material-cost-trend`, filter periode; grafik omzet harian & per channel | Belum ada filter channel/produk/status, KPI packaging/iklan/AOV, grafik per komponen biaya |
| J. Laporan (10 jenis) + export Excel/CSV/PDF | **Sebagian** | `reports/sales, hpp, products, channels, profit-loss, cash-flow, expenses, purchases, production`; frontend punya `xlsx` & `jspdf` di dependencies | Belum ada: laporan packaging, marketplace fee, advertising, settlement, rekonsiliasi |
| K. Inventory: satu titik pengurangan stok, tidak untuk Pending/Batal/Refund | **Sebagian** | `post_inventory` satu titik; `apply_sale` langsung mengurangi stok saat dibuat; `reverse_ref` saat hapus/edit | Tidak ada konsep status → semua sale mengurangi stok saat dibuat. Perlu aturan "kurangi stok saat status ≥ Diproses/Dikirim" dan `reverse_ref` saat Batal/Refund |
| L. Koleksi baru | — | `sales`, `channels`, `cash_transactions`, `inventory_transactions`, `expenses` (kategori "Iklan", "Marketplace") | Kandidat baru: `sales_orders`(perluasan `sales`), `sales_fees`, `packaging_items`, `packaging_costs`, `marketplace_imports`, `marketplace_settlements`, `sales_reconciliation`. **Rekomendasi**: perluas dokumen `sales` (tambah field) daripada koleksi paralel, agar laporan/dashboard/kas lama tetap konsisten |
| M. Keamanan | **OK** | JWT + bcrypt, isolasi `business_id` via `Q()` | Tidak ada API marketplace — sesuai permintaan |
| N. UI/UX | **Ada dasar** | shadcn/ui, `lib/format.js` (Rp, tanggal ID), tabel, filter tanggal, recharts | Halaman baru: Penjualan Marketplace, Packaging, Import, Settlement, Rekonsiliasi, Pengaturan Biaya |

## Perubahan yang dilakukan (ringkas)

| File | Aksi |
|---|---|
| `backend/requirements.txt` | ditulis ulang, 18 paket yang dipakai, versi identik freeze asli |
| `backend/requirements.emergent-image.txt` | freeze asli (referensi) |
| `backend/requirements.lock` | baru — pip freeze venv bersih 3.11 |
| `backend/.env.example`, `backend/Dockerfile`, `backend/.dockerignore`, `backend/.python-version`, `backend/runtime.txt` | baru |
| `frontend/yarn.lock`, `frontend/.env.example`, `frontend/vercel.json`, `frontend/.nvmrc` | baru |
| `.gitignore` | tambah `!.env.example` (sebelumnya `.env.*` ikut mengabaikan contoh env) |
| `memory/test_credentials.md` | akun admin baru (`admin@keuangan.id`) |
| Kode aplikasi (`*.py`, `src/**`) | **tidak diubah** |
