# PRD — Keuangan-V1 (Aplikasi Keuangan & HPP UMKM)

## Problem statement (asli, ringkas)
Import repo `danarhuda59-commits/Keuangan-V1` (branch `main`) ke workspace baru, install dependency sesuai lockfile, `.env.example`, audit credential, admin baru dari env, Dockerfile backend, smoke test, `README-setup.md`, laporan audit fitur (Fase 5). **Bukan** membangun fitur baru. Setelah audit: fitur "Keuangan Penjualan Marketplace & Website + Biaya Beban Packaging" sebagai plan terpisah (spesifikasi lengkap A–O ada di pesan user).

## Pilihan user
- Repo public (tanpa token); runtime fallback = Node 20 / Python 3.11 workspace; MongoDB lokal workspace; admin baru password acak di env; lanjut ke fitur marketplace setelah audit (tunggu konfirmasi).

## Arsitektur
- `backend/` FastAPI 0.110 (Python 3.11), Motor, PyJWT + bcrypt, semua route prefix `/api`; `core.py` (HPP engine, ledger) + 5 router
- `frontend/` React 19 CRA + CRACO 7, Tailwind, shadcn/ui, SWR/axios; `src/lib/api.js` → `REACT_APP_BACKEND_URL`
- MongoDB (lokal dev → Atlas prod); S3-compatible storage opsional

## Persona
Pemilik/operator UMKM F&B: HPP dari bahan & resep, pembelian/produksi/penjualan, laporan; menjual via Shopee/TikTok/Tokopedia/Website.

## Yang sudah dikerjakan (Juni 2026 — re-import)
- [x] Marketplace & Packaging (iterasi 6): router `backend/routers/marketplace.py` (prefix `/api/marketplace`) — fees (sales_fees), packaging_items + packaging_costs + `products.packaging_cost_id`, sales_orders (rumus C, status, stok satu titik via `stock_deducted`), import CSV/XLSX (preview→validate→commit, dedup order_id+sku, marketplace_imports), marketplace_settlements (+kas masuk), reconciliation, dashboard, reports/{10 tipe}. Frontend `src/pages/marketplace/*` + nav group "Marketplace". Smoke: `backend/tests/smoke_marketplace.py` + testing agent iterasi 6 lulus.
- [x] Keputusan desain: order marketplace TIDAK ikut ke koleksi `sales`/Laba Rugi lama (menghindari double counting) — profit marketplace dilihat di Dashboard/Laporan Marketplace; payout masuk kas via settlement. HPP order = `products.avg_hpp` saat order (snapshot).
- [x] Fase 0–1: clone histori utuh (7 commit), branch default `main`, runtime terdeteksi (.nvmrc 20, .python-version 3.11), credential scan bersih
- [x] Fase 2: `yarn install` (yarn.lock tidak ada di repo → dibuat), `pip install -r requirements.txt` + `requirements.lock` dari venv bersih, warning dicatat
- [x] Fase 3: `.env.example` x2, JWT_SECRET + ADMIN_* di backend/.env, backend & frontend jalan, login OK, `GET /api/health`
- [x] Fase 4: `scripts/create_admin.py`, Dockerfile multi-stage non-root (belum bisa di-build: tanpa Docker di workspace), `README-setup.md`, 16 unit test lulus, `CI=true yarn build` lolos
- [x] Fase 5: gap analysis fitur marketplace/packaging di `AUDIT.md`

## Backlog prioritas
- P1 (marketplace, lanjutan): integrasi order marketplace ke Laba Rugi utama (opsi toggle), refund parsial per item, pengaturan biaya per kategori produk, template mapping tersimpan per channel, multi-item per Order ID dalam satu form
- P0 (fitur berikutnya, menunggu go): Marketplace & Packaging — urutan saran: (1) pengaturan biaya channel, (2) packaging items/costs per SKU, (3) perluasan `sales` → order marketplace dengan status & inventory by-status, (4) import dengan mapping + dedup Order ID, (5) settlement + rekonsiliasi, (6) dashboard/laporan/export
- P1 (dari AUDIT.md): RBAC owner-only untuk restore/demo/users; token di query string; rate limit register
- P2: Decimal/integer rupiah; lifespan API; `@emergentbase/*` → optionalDependencies; commit `yarn.lock` & `requirements.lock`

## Catatan operasional
- Kredensial dev: `memory/test_credentials.md`. Docker build harus diverifikasi di mesin dengan Docker.
