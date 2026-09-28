import io, uuid, json, logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response, Request
from typing import Optional, List, Any
from pydantic import BaseModel
import pandas as pd
from core import db, Q, new_id, now_iso, today_str, TZ, strip, num, current_user, audit, hash_password
from routers.master import MaterialIn, ProductIn, create_material, create_product
from routers.recipes import RecipeIn, create_recipe
from routers.operations import PurchaseIn, SaleIn, ExpenseIn, ProductionIn, create_purchase, create_sale, create_expense, create_production
import storage

router = APIRouter(tags=["settings"])
logger = logging.getLogger(__name__)
APP_NAME = "hpp-finance"


BUSINESS_COLLECTIONS = ["categories", "units", "unit_conversions", "suppliers", "raw_materials", "material_price_history", "products", "recipes", "recipe_items",
                        "production_orders", "production_items", "inventory_transactions", "purchases", "sales", "expenses", "cash_accounts", "cash_transactions",
                        "channels", "bep_calculations", "hpp_calculations", "audit_logs", "counters", "files"]


# ---------- Business & users ----------
class BusinessIn(BaseModel):
    name: str
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    logo_url: Optional[str] = ""
    target_margin: float = 30
    notes: Optional[str] = ""


@router.get("/business")
async def get_business(user=Depends(current_user)):
    return strip(await db.businesses.find_one({"id": user["business_id"]}, {"_id": 0}))


@router.put("/business")
async def update_business(body: BusinessIn, user=Depends(current_user)):
    if not body.name.strip():
        raise HTTPException(400, "Nama usaha wajib diisi")
    await db.businesses.update_one({"id": user["business_id"]}, {"$set": {**body.model_dump(), "updated_at": now_iso()}})
    await audit(user["business_id"], user, "update", "businesses", user["business_id"])
    return await get_business(user)


class UserIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "staff"


@router.get("/users")
async def list_users(user=Depends(current_user)):
    return await db.users.find({"business_id": user["business_id"]}, {"_id": 0, "password_hash": 0}).to_list(100)


@router.post("/users")
async def add_user(body: UserIn, user=Depends(current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "Hanya owner yang dapat menambah user")
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email sudah terdaftar")
    if len(body.password) < 6:
        raise HTTPException(400, "Password minimal 6 karakter")
    doc = {"id": new_id(), "business_id": user["business_id"], "name": body.name, "email": email, "role": body.role, "created_at": now_iso()}
    await db.users.insert_one({**doc, "password_hash": hash_password(body.password)})
    await audit(user["business_id"], user, "create", "users", doc["id"])
    return doc


@router.delete("/users/{uid}")
async def remove_user(uid: str, user=Depends(current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "Hanya owner yang dapat menghapus user")
    if uid == user["id"]:
        raise HTTPException(400, "Tidak dapat menghapus diri sendiri")
    await db.users.delete_one({"id": uid, "business_id": user["business_id"]})
    return {"ok": True}


# ---------- Files ----------
@router.post("/upload")
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Ukuran file maksimal 5MB")
    ext = (file.filename or "bin").rsplit(".", 1)[-1].lower()
    path = f"{APP_NAME}/uploads/{user['business_id']}/{uuid.uuid4()}.{ext}"
    ct = file.content_type or "application/octet-stream"
    if not ct.startswith("image/"):
        raise HTTPException(400, "Hanya file gambar yang diperbolehkan")
    try:
        spath = storage.put_object(path, data, ct)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"upload failed: {e}")
        raise HTTPException(502, "Upload ke storage gagal, coba lagi")
    fid = new_id()
    await db.files.insert_one({"id": fid, "business_id": user["business_id"], "storage_path": spath, "original_filename": file.filename, "content_type": ct, "size": len(data), "is_deleted": False, "created_at": now_iso()})
    return {"id": fid, "url": f"/api/files/{fid}", "filename": file.filename}


@router.get("/files/{fid}")
async def get_file(fid: str, user=Depends(current_user)):
    rec = await db.files.find_one({"id": fid, "business_id": user["business_id"], "is_deleted": False})
    if not rec:
        raise HTTPException(404, "File tidak ditemukan")
    try:
        content, ct = storage.get_object(rec["storage_path"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"download failed: {e}")
        raise HTTPException(502, "Gagal mengambil file dari storage")
    return Response(content=content, media_type=rec.get("content_type") or ct, headers={"Cache-Control": "private, max-age=3600"})


# ---------- Backup / restore ----------
@router.get("/backup")
async def backup(user=Depends(current_user)):
    bid = user["business_id"]
    out = {"version": 1, "exported_at": now_iso(), "business": strip(await db.businesses.find_one({"id": bid}, {"_id": 0})), "collections": {}}
    for c in BUSINESS_COLLECTIONS:
        out["collections"][c] = await db[c].find({"business_id": bid}, {"_id": 0}).to_list(200000)
    await audit(bid, user, "backup", "businesses", bid)
    return out


@router.post("/restore")
async def restore(file: UploadFile = File(...), user=Depends(current_user)):
    bid = user["business_id"]
    try:
        data = json.loads((await file.read()).decode("utf-8"))
        cols = data["collections"]
    except Exception:
        raise HTTPException(400, "File backup tidak valid")
    for c in BUSINESS_COLLECTIONS:
        await db[c].delete_many({"business_id": bid})
        rows = [{**r, "business_id": bid} for r in cols.get(c, [])]
        if rows:
            await db[c].insert_many(rows)
    if data.get("business"):
        b = {k: v for k, v in data["business"].items() if k not in ("id", "owner_email")}
        await db.businesses.update_one({"id": bid}, {"$set": b})
    await audit(bid, user, "restore", "businesses", bid, {"collections": {k: len(v) for k, v in cols.items()}})
    return {"ok": True, "restored": {k: len(v) for k, v in cols.items()}}


# ---------- Import ----------
IMPORT_TEMPLATES = {
    "materials": {"columns": ["kode", "nama", "kategori", "satuan_beli", "satuan_pakai", "faktor_konversi", "harga_beli", "min_stok", "stok_awal", "catatan"], "required": ["nama", "satuan_beli", "satuan_pakai"], "numeric": ["faktor_konversi", "harga_beli", "min_stok", "stok_awal"],
                  "example": ["BHN-001", "Tapioka", "Bahan Utama", "kg", "gram", "1000", "10000", "5000", "20000", ""]},
    "products": {"columns": ["sku", "nama", "kategori", "satuan", "harga_jual", "min_stok", "deskripsi"], "required": ["nama"], "numeric": ["harga_jual", "min_stok"], "example": ["SKU-001", "Baso Aci Original", "Makanan", "cup", "12000", "10", ""]},
    "suppliers": {"columns": ["kode", "nama", "kontak", "telepon", "email", "alamat", "catatan"], "required": ["nama"], "numeric": [], "example": ["SUP-001", "Toko Bahan Jaya", "Budi", "0812xxx", "", "Bandung", ""]},
    "recipes": {"columns": ["nama_resep", "produk", "yield", "satuan_yield", "harga_jual", "bahan", "qty", "satuan", "waste_pct"], "required": ["nama_resep", "bahan", "qty"], "numeric": ["yield", "harga_jual", "qty", "waste_pct"],
                "example": ["Baso Aci v1", "Baso Aci Original", "20", "cup", "12000", "Tapioka", "1500", "gram", "5"]},
    "purchases": {"columns": ["tanggal", "supplier", "bahan", "qty", "satuan", "harga", "metode_bayar", "status_bayar"], "required": ["bahan", "qty", "harga"], "numeric": ["qty", "harga"], "example": ["2025-01-05", "Toko Bahan Jaya", "Tapioka", "10", "kg", "10000", "Tunai", "paid"]},
    "sales": {"columns": ["tanggal", "channel", "produk", "qty", "harga", "diskon", "biaya_platform"], "required": ["produk", "qty", "harga"], "numeric": ["qty", "harga", "diskon", "biaya_platform"], "example": ["2025-01-06", "Offline", "Baso Aci Original", "5", "12000", "0", "0"]},
}


@router.get("/import/template/{itype}")
async def import_template(itype: str, user=Depends(current_user)):
    t = IMPORT_TEMPLATES.get(itype)
    if not t:
        raise HTTPException(404, "Template tidak ditemukan")
    df = pd.DataFrame([t["example"]], columns=t["columns"])
    return Response(content=df.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=template_{itype}.csv"})


def read_table(data: bytes, filename: str):
    try:
        if filename.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(data))
        else:
            df = pd.read_csv(io.BytesIO(data), sep=None, engine="python")
    except Exception as e:
        raise HTTPException(400, f"File tidak dapat dibaca: {e}")
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.fillna("")


@router.post("/import/preview")
async def import_preview(itype: str = Form(...), file: UploadFile = File(...), user=Depends(current_user)):
    t = IMPORT_TEMPLATES.get(itype)
    if not t:
        raise HTTPException(400, "Tipe import tidak dikenal")
    df = read_table(await file.read(), file.filename or "")
    missing = [c for c in t["required"] if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Kolom wajib tidak ditemukan: {', '.join(missing)}. Kolom yang tersedia: {', '.join(df.columns)}")
    rows = []
    for i, r in df.iterrows():
        data = {c: (str(r[c]).strip() if c in df.columns else "") for c in t["columns"]}
        errors = [f"Kolom '{c}' wajib diisi" for c in t["required"] if not data.get(c)]
        for c in t["numeric"]:
            if data.get(c):
                try:
                    v = float(str(data[c]).replace(".", "").replace(",", ".")) if str(data[c]).count(".") > 1 else float(str(data[c]).replace(",", "."))
                    if v < 0:
                        errors.append(f"Kolom '{c}' tidak boleh negatif")
                    data[c] = v
                except ValueError:
                    errors.append(f"Kolom '{c}' harus angka")
            else:
                data[c] = 0
        rows.append({"row": i + 2, "data": data, "errors": errors})
    return {"type": itype, "columns": t["columns"], "rows": rows, "valid_count": sum(1 for r in rows if not r["errors"]), "error_count": sum(1 for r in rows if r["errors"])}


class ImportCommit(BaseModel):
    type: str
    rows: List[dict]


async def lookup(bid, coll, name, fields):
    if not name:
        return None
    for f in fields:
        d = await db[coll].find_one(Q(bid, **{f: {"$regex": f"^{__import__('re').escape(str(name))}$", "$options": "i"}}), {"_id": 0})
        if d:
            return d
    return None


@router.post("/import/commit")
async def import_commit(body: ImportCommit, user=Depends(current_user)):
    bid = user["business_id"]
    ok, errors = 0, []
    if body.type == "recipes":
        groups = {}
        for r in body.rows:
            groups.setdefault(r["nama_resep"], []).append(r)
        for name, rows in groups.items():
            try:
                items = []
                for r in rows:
                    m = await lookup(bid, "raw_materials", r.get("bahan"), ["code", "name"])
                    if not m:
                        raise HTTPException(400, f"Bahan '{r.get('bahan')}' tidak ditemukan")
                    items.append({"material_id": m["id"], "qty": float(r.get("qty") or 0), "unit": r.get("satuan") or m["usage_unit"], "waste_pct": float(r.get("waste_pct") or 0)})
                p = await lookup(bid, "products", rows[0].get("produk"), ["sku", "name"])
                await create_recipe(RecipeIn(product_id=p["id"] if p else None, name=name, yield_qty=float(rows[0].get("yield") or 1), yield_unit=rows[0].get("satuan_yield") or "pcs", selling_price=float(rows[0].get("harga_jual") or 0), items=items), user)
                ok += 1
            except HTTPException as e:
                errors.append(f"Resep '{name}': {e.detail}")
        return {"imported": ok, "errors": errors}
    for r in body.rows:
        try:
            if body.type == "materials":
                cat = await lookup(bid, "categories", r.get("kategori"), ["name"])
                await create_material(MaterialIn(code=r.get("kode") or "", name=r["nama"], category_id=cat["id"] if cat else None, purchase_unit=r["satuan_beli"], usage_unit=r["satuan_pakai"], conversion_factor=float(r.get("faktor_konversi") or 1),
                                                 last_price=float(r.get("harga_beli") or 0), min_stock=float(r.get("min_stok") or 0), initial_stock=float(r.get("stok_awal") or 0), notes=r.get("catatan") or ""), user)
            elif body.type == "products":
                cat = await lookup(bid, "categories", r.get("kategori"), ["name"])
                await create_product(ProductIn(sku=r.get("sku") or "", name=r["nama"], category_id=cat["id"] if cat else None, unit=r.get("satuan") or "pcs", selling_price=float(r.get("harga_jual") or 0), min_stock=float(r.get("min_stok") or 0), description=r.get("deskripsi") or ""), user)
            elif body.type == "suppliers":
                doc = {"id": new_id(), "business_id": bid, "code": r.get("kode") or "", "name": r["nama"], "contact_name": r.get("kontak") or "", "phone": str(r.get("telepon") or ""), "email": r.get("email") or "", "address": r.get("alamat") or "", "notes": r.get("catatan") or "", "is_active": True, "created_at": now_iso(), "updated_at": now_iso()}
                await db.suppliers.insert_one(doc)
            elif body.type == "purchases":
                m = await lookup(bid, "raw_materials", r.get("bahan"), ["code", "name"])
                if not m:
                    raise HTTPException(400, f"Bahan '{r.get('bahan')}' tidak ditemukan")
                s = await lookup(bid, "suppliers", r.get("supplier"), ["code", "name"])
                await create_purchase(PurchaseIn(date=r.get("tanggal") or None, supplier_id=s["id"] if s else None, items=[{"material_id": m["id"], "qty": float(r["qty"]), "unit": r.get("satuan") or m["purchase_unit"], "price": float(r["harga"])}],
                                                 payment_method=r.get("metode_bayar") or "Tunai", payment_status=r.get("status_bayar") or "paid"), user)
            elif body.type == "sales":
                p = await lookup(bid, "products", r.get("produk"), ["sku", "name"])
                if not p:
                    raise HTTPException(400, f"Produk '{r.get('produk')}' tidak ditemukan")
                await create_sale(SaleIn(date=r.get("tanggal") or None, channel=r.get("channel") or "Offline", items=[{"product_id": p["id"], "qty": float(r["qty"]), "price": float(r["harga"]), "discount": float(r.get("diskon") or 0)}], platform_fee=float(r.get("biaya_platform") or 0)), user)
            else:
                raise HTTPException(400, "Tipe import tidak dikenal")
            ok += 1
        except HTTPException as e:
            errors.append(f"Baris {r.get('_row', '?')} ({r.get('nama') or r.get('bahan') or r.get('produk') or ''}): {e.detail}")
    await audit(bid, user, "import", body.type, None, {"imported": ok, "errors": len(errors)})
    return {"imported": ok, "errors": errors}


# ---------- Demo data ----------
@router.post("/demo/seed")
async def seed_demo(user=Depends(current_user)):
    bid = user["business_id"]
    if await db.raw_materials.find_one({"business_id": bid, "is_demo": True}):
        raise HTTPException(400, "Demo data sudah ada. Hapus demo data terlebih dahulu")
    start_ts = now_iso()
    cats = {c["name"]: c["id"] for c in await db.categories.find(Q(bid), {"_id": 0}).to_list(100)}
    sup_docs = [("SUP-DEMO-1", "Toko Bahan Pokok Sejahtera", "Pak Budi", "081200001111", "Jl. Pasar Baru No. 12"), ("SUP-DEMO-2", "Grosir Kemasan Mandiri", "Ibu Sari", "081300002222", "Jl. Industri No. 5")]
    sups = []
    for code, name, contact, phone, addr in sup_docs:
        d = {"id": new_id(), "business_id": bid, "code": code, "name": name, "contact_name": contact, "phone": phone, "email": "", "address": addr, "notes": "", "is_active": True, "is_demo": True, "created_at": now_iso(), "updated_at": now_iso()}
        await db.suppliers.insert_one(dict(d))
        sups.append(d)
    mat_defs = [("Tapioka", "Bahan Utama", "kg", "gram", 1000, 9500, 5000, 0), ("Tepung Terigu", "Bahan Utama", "kg", "gram", 1000, 12000, 3000, 0), ("Bawang Putih", "Bumbu & Rempah", "kg", "gram", 1000, 35000, 500, 0),
                ("Garam", "Bumbu & Rempah", "kg", "gram", 1000, 8000, 500, 0), ("Penyedap Rasa", "Bumbu & Rempah", "kg", "gram", 1000, 45000, 300, 0), ("Cabai Bubuk", "Bumbu & Rempah", "kg", "gram", 1000, 80000, 1200, 0),
                ("Minyak Goreng", "Bahan Pelengkap", "liter", "ml", 1000, 17000, 2000, 0), ("Daun Bawang", "Bahan Pelengkap", "kg", "gram", 1000, 20000, 300, 0), ("Air", "Bahan Pelengkap", "liter", "ml", 1000, 500, 5000, 0),
                ("Cup Kemasan 300ml", "Kemasan", "pack", "pcs", 50, 35000, 100, 1), ("Stiker Label", "Kemasan", "lembar", "pcs", 12, 6000, 100, 1), ("Sambal Sachet", "Bahan Pelengkap", "pack", "pcs", 100, 45000, 100, 1)]
    mats = {}
    for name, cat, pu, uu, cf, price, minq, sup in mat_defs:
        m = await create_material(MaterialIn(name=name, category_id=cats.get(cat), purchase_unit=pu, usage_unit=uu, conversion_factor=cf, last_price=price, supplier_id=sups[sup]["id"], min_stock=minq), user)
        mats[name] = m
    prod_defs = [("Baso Aci Original", "Makanan", "cup", 12000, 10), ("Cireng Bumbu Rujak", "Frozen Food", "pack", 15000, 10), ("Seblak Kering Pedas", "Snack", "pack", 10000, 25)]
    prods = {}
    for name, cat, unit, price, minq in prod_defs:
        prods[name] = await create_product(ProductIn(name=name, category_id=cats.get(cat), unit=unit, selling_price=price, min_stock=minq, description="Produk demo"), user)
    def item(n, q, u=None, w=0):
        return {"material_id": mats[n]["id"], "qty": q, "unit": u or mats[n]["usage_unit"], "waste_pct": w}
    adonan = await create_recipe(RecipeIn(name="Adonan Baso Aci (Sub-resep)", is_sub_recipe=True, yield_qty=1000, yield_unit="gram", items=[item("Tapioka", 700, w=2), item("Tepung Terigu", 150), item("Bawang Putih", 30), item("Garam", 15), item("Penyedap Rasa", 10), item("Air", 400)]), user)
    r1 = await create_recipe(RecipeIn(product_id=prods["Baso Aci Original"]["id"], name="Baso Aci Original v1", yield_qty=20, yield_unit="cup", selling_price=12000, is_default=True,
                                      items=[{"sub_recipe_id": adonan["id"], "qty": 1600, "unit": "gram", "waste_pct": 0}, item("Cabai Bubuk", 60), item("Minyak Goreng", 100), item("Daun Bawang", 50), item("Bawang Putih", 40), item("Garam", 20), item("Penyedap Rasa", 15), item("Air", 3000), item("Sambal Sachet", 20), item("Cup Kemasan 300ml", 20), item("Stiker Label", 20)],
                                      extra_costs=[{"name": "Gas & listrik", "type": "overhead", "method": "per_batch", "value": 8000}, {"name": "Tenaga kerja", "type": "labor", "method": "per_batch", "value": 25000}, {"name": "Plastik pembungkus", "type": "packaging", "method": "per_unit", "value": 300}]), user)
    r2 = await create_recipe(RecipeIn(product_id=prods["Cireng Bumbu Rujak"]["id"], name="Cireng Rujak v1", yield_qty=25, yield_unit="pack", selling_price=15000, is_default=True,
                                      items=[item("Tapioka", 2500, w=3), item("Tepung Terigu", 500), item("Bawang Putih", 80), item("Garam", 40), item("Penyedap Rasa", 20), item("Daun Bawang", 100), item("Air", 1500), item("Cabai Bubuk", 150), item("Minyak Goreng", 300), item("Cup Kemasan 300ml", 25), item("Stiker Label", 25)],
                                      extra_costs=[{"name": "Gas", "type": "overhead", "method": "per_batch", "value": 6000}, {"name": "Tenaga kerja", "type": "labor", "method": "per_batch", "value": 30000}, {"name": "Overhead lain", "type": "other", "method": "pct_material", "value": 5}]), user)
    r3 = await create_recipe(RecipeIn(product_id=prods["Seblak Kering Pedas"]["id"], name="Seblak Kering v1", yield_qty=30, yield_unit="pack", selling_price=10000, is_default=True,
                                      items=[item("Tapioka", 1500, w=5), item("Tepung Terigu", 300), item("Cabai Bubuk", 200), item("Bawang Putih", 100), item("Garam", 40), item("Penyedap Rasa", 30), item("Minyak Goreng", 800), item("Daun Bawang", 60), item("Cup Kemasan 300ml", 30), item("Stiker Label", 30)],
                                      extra_costs=[{"name": "Gas & minyak goreng ulang", "type": "overhead", "method": "per_batch", "value": 12000}, {"name": "Tenaga kerja", "type": "labor", "method": "per_unit", "value": 700}]), user)
    today = datetime.now(TZ).date()
    d = lambda n: (today - timedelta(days=n)).isoformat()
    await create_purchase(PurchaseIn(date=d(20), supplier_id=sups[0]["id"], items=[{"material_id": mats["Tapioka"]["id"], "qty": 30, "unit": "kg", "price": 8700}, {"material_id": mats["Tepung Terigu"]["id"], "qty": 10, "unit": "kg", "price": 12000}, {"material_id": mats["Bawang Putih"]["id"], "qty": 3, "unit": "kg", "price": 35000},
                                     {"material_id": mats["Garam"]["id"], "qty": 2, "unit": "kg", "price": 8000}, {"material_id": mats["Penyedap Rasa"]["id"], "qty": 1, "unit": "kg", "price": 45000}, {"material_id": mats["Cabai Bubuk"]["id"], "qty": 2, "unit": "kg", "price": 80000},
                                     {"material_id": mats["Minyak Goreng"]["id"], "qty": 10, "unit": "liter", "price": 17000}, {"material_id": mats["Daun Bawang"]["id"], "qty": 2, "unit": "kg", "price": 20000}, {"material_id": mats["Air"]["id"], "qty": 100, "unit": "liter", "price": 500}], payment_method="Transfer Bank"), user)
    await create_purchase(PurchaseIn(date=d(18), supplier_id=sups[1]["id"], items=[{"material_id": mats["Cup Kemasan 300ml"]["id"], "qty": 10, "unit": "pack", "price": 35000}, {"material_id": mats["Stiker Label"]["id"], "qty": 40, "unit": "lembar", "price": 6000}, {"material_id": mats["Sambal Sachet"]["id"], "qty": 3, "unit": "pack", "price": 45000}], payment_method="Kredit/Tempo", payment_status="unpaid"), user)
    await create_purchase(PurchaseIn(date=d(8), supplier_id=sups[0]["id"], items=[{"material_id": mats["Tapioka"]["id"], "qty": 20, "unit": "kg", "price": 9500}, {"material_id": mats["Minyak Goreng"]["id"], "qty": 5, "unit": "liter", "price": 17500}], payment_method="Tunai"), user)
    await create_production(ProductionIn(product_id=prods["Baso Aci Original"]["id"], recipe_id=r1["id"], date=d(15), batch_count=3, qty_produced=60, operator="Tim Produksi"), user)
    await create_production(ProductionIn(product_id=prods["Cireng Bumbu Rujak"]["id"], recipe_id=r2["id"], date=d(14), batch_count=2, qty_produced=50, operator="Tim Produksi"), user)
    await create_production(ProductionIn(product_id=prods["Seblak Kering Pedas"]["id"], recipe_id=r3["id"], date=d(12), batch_count=2, qty_produced=60, operator="Tim Produksi"), user)
    await create_production(ProductionIn(product_id=prods["Baso Aci Original"]["id"], recipe_id=r1["id"], date=d(5), batch_count=2, qty_produced=40, operator="Tim Produksi"), user)
    sales_plan = [(13, "Offline", "Baso Aci Original", 8, 0), (13, "WhatsApp", "Cireng Bumbu Rujak", 5, 0), (12, "Shopee", "Baso Aci Original", 10, 6000), (11, "Offline", "Seblak Kering Pedas", 12, 0), (10, "TikTok Shop", "Cireng Bumbu Rujak", 8, 5000),
                  (9, "Offline", "Baso Aci Original", 6, 0), (8, "Tokopedia", "Seblak Kering Pedas", 10, 4000), (7, "WhatsApp", "Baso Aci Original", 9, 0), (6, "Shopee", "Cireng Bumbu Rujak", 7, 4500), (5, "Offline", "Seblak Kering Pedas", 8, 0),
                  (4, "Offline", "Baso Aci Original", 12, 0), (3, "Website", "Cireng Bumbu Rujak", 6, 0), (2, "Shopee", "Baso Aci Original", 10, 6000), (1, "Offline", "Seblak Kering Pedas", 9, 0), (0, "WhatsApp", "Baso Aci Original", 7, 0), (0, "Offline", "Cireng Bumbu Rujak", 4, 0)]
    for days, ch, pn, qty, fee in sales_plan:
        p = prods[pn]
        await create_sale(SaleIn(date=d(days), channel=ch, items=[{"product_id": p["id"], "qty": qty, "price": p["selling_price"]}], platform_fee=fee, payment_method="Tunai" if ch == "Offline" else "Marketplace" if fee else "Transfer Bank"), user)
    for days, cat, desc, amt in [(19, "Sewa", "Sewa dapur produksi bulan ini", 1500000), (16, "Listrik", "Token listrik", 300000), (14, "Marketing", "Cetak brosur & banner", 250000), (10, "Iklan", "Iklan Shopee Ads", 200000), (9, "Transportasi", "Bensin pengiriman", 150000), (6, "Gaji", "Gaji harian tim produksi", 900000), (3, "Internet", "Paket internet", 150000), (1, "Peralatan", "Spatula & wadah adonan", 175000)]:
        await create_expense(ExpenseIn(date=d(days), category=cat, description=desc, amount=amt), user)
    from core import post_cash
    await post_cash(bid, None, "in", 6000000, "capital", "manual", new_id(), "Modal awal usaha (demo)", d(21))
    for c in BUSINESS_COLLECTIONS:
        await db[c].update_many({"business_id": bid, "created_at": {"$gte": start_ts}}, {"$set": {"is_demo": True}})
    await audit(bid, user, "seed_demo", "businesses", bid)
    return {"ok": True}


async def recompute_stocks(bid):
    for coll, kind in ((db.raw_materials, "material"), (db.products, "product")):
        for it in await coll.find({"business_id": bid}, {"_id": 0, "id": 1}).to_list(10000):
            txs = await db.inventory_transactions.find({"business_id": bid, "item_type": kind, "item_id": it["id"]}, {"_id": 0, "direction": 1, "qty": 1}).to_list(100000)
            stock = sum(t["qty"] if t["direction"] == "in" else -t["qty"] for t in txs)
            await coll.update_one({"id": it["id"]}, {"$set": {"stock": max(stock, 0)}})


@router.delete("/demo")
async def delete_demo(user=Depends(current_user)):
    bid = user["business_id"]
    removed = {}
    for c in BUSINESS_COLLECTIONS:
        res = await db[c].delete_many({"business_id": bid, "is_demo": True})
        if res.deleted_count:
            removed[c] = res.deleted_count
    await recompute_stocks(bid)
    await audit(bid, user, "delete_demo", "businesses", bid, removed)
    return {"ok": True, "removed": removed}


@router.get("/demo/status")
async def demo_status(user=Depends(current_user)):
    return {"has_demo": bool(await db.raw_materials.find_one({"business_id": user["business_id"], "is_demo": True}))}
