from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from core import db, Q, new_id, now_iso, strip, num, current_user, audit, post_inventory, price_per_usage, next_number

router = APIRouter(tags=["master"])


class CategoryIn(BaseModel):
    name: str
    type: str = "material"


class UnitIn(BaseModel):
    code: str
    name: str = ""


class ConversionIn(BaseModel):
    from_unit: str
    to_unit: str
    factor: float


class SupplierIn(BaseModel):
    code: Optional[str] = ""
    name: str
    contact_name: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    address: Optional[str] = ""
    notes: Optional[str] = ""
    is_active: bool = True


class MaterialIn(BaseModel):
    code: Optional[str] = ""
    name: str
    category_id: Optional[str] = None
    purchase_unit: str
    usage_unit: str
    conversion_factor: float = 1
    last_price: float = 0
    supplier_id: Optional[str] = None
    min_stock: float = 0
    initial_stock: Optional[float] = None
    is_active: bool = True
    notes: Optional[str] = ""


class ProductIn(BaseModel):
    sku: Optional[str] = ""
    name: str
    category_id: Optional[str] = None
    unit: str = "pcs"
    selling_price: float = 0
    photo_url: Optional[str] = ""
    description: Optional[str] = ""
    min_stock: float = 0
    is_active: bool = True


async def get_or_404(coll, bid, id_, label):
    doc = await coll.find_one(Q(bid, id=id_), {"_id": 0})
    if not doc:
        raise HTTPException(404, f"{label} tidak ditemukan")
    return doc


def simple_crud(path, coll_name, Model, label, unique_field=None):
    coll = db[coll_name]

    @router.get(f"/{path}")
    async def list_items(user=Depends(current_user), q: str = "", type: str = ""):
        query = Q(user["business_id"])
        if q:
            query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"code": {"$regex": q, "$options": "i"}}]
        if type:
            query["type"] = type
        return await coll.find(query, {"_id": 0}).sort("name", 1).to_list(5000)

    @router.post(f"/{path}")
    async def create_item(body: Model, user=Depends(current_user)):
        bid = user["business_id"]
        data = body.model_dump()
        if not (data.get("name") or data.get("code") or "").strip():
            raise HTTPException(400, f"Nama {label} wajib diisi")
        if unique_field and await coll.find_one(Q(bid, **{unique_field: data[unique_field]})):
            raise HTTPException(400, f"{label} '{data[unique_field]}' sudah ada")
        doc = {"id": new_id(), "business_id": bid, **data, "created_at": now_iso(), "updated_at": now_iso()}
        await coll.insert_one(dict(doc))
        await audit(bid, user, "create", coll_name, doc["id"], {"name": data.get("name")})
        return doc

    @router.put(f"/{path}/{{item_id}}")
    async def update_item(item_id: str, body: Model, user=Depends(current_user)):
        bid = user["business_id"]
        await get_or_404(coll, bid, item_id, label)
        data = body.model_dump()
        await coll.update_one({"id": item_id}, {"$set": {**data, "updated_at": now_iso()}})
        await audit(bid, user, "update", coll_name, item_id)
        return strip(await coll.find_one({"id": item_id}, {"_id": 0}))

    @router.delete(f"/{path}/{{item_id}}")
    async def delete_item(item_id: str, user=Depends(current_user)):
        bid = user["business_id"]
        await get_or_404(coll, bid, item_id, label)
        await coll.update_one({"id": item_id}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
        await audit(bid, user, "delete", coll_name, item_id)
        return {"ok": True}


simple_crud("categories", "categories", CategoryIn, "Kategori")
simple_crud("units", "units", UnitIn, "Satuan", unique_field="code")
simple_crud("suppliers", "suppliers", SupplierIn, "Supplier")


@router.get("/unit-conversions")
async def list_conversions(user=Depends(current_user)):
    return await db.unit_conversions.find({"business_id": user["business_id"]}, {"_id": 0}).to_list(2000)


@router.post("/unit-conversions")
async def create_conversion(body: ConversionIn, user=Depends(current_user)):
    num(body.factor, "Faktor konversi", 0, allow_equal=False)
    if body.from_unit == body.to_unit:
        raise HTTPException(400, "Satuan asal dan tujuan tidak boleh sama")
    doc = {"id": new_id(), "business_id": user["business_id"], **body.model_dump(), "created_at": now_iso()}
    await db.unit_conversions.delete_many({"business_id": user["business_id"], "from_unit": body.from_unit, "to_unit": body.to_unit})
    await db.unit_conversions.insert_one(dict(doc))
    return doc


@router.delete("/unit-conversions/{cid}")
async def delete_conversion(cid: str, user=Depends(current_user)):
    await db.unit_conversions.delete_one({"id": cid, "business_id": user["business_id"]})
    return {"ok": True}


@router.get("/suppliers/{sid}/purchases")
async def supplier_purchases(sid: str, user=Depends(current_user)):
    rows = await db.purchases.find(Q(user["business_id"], supplier_id=sid), {"_id": 0}).sort("date", -1).to_list(2000)
    return {"purchases": rows, "total": sum(p.get("total", 0) for p in rows), "count": len(rows)}


# ---------- Raw materials ----------
def enrich_material(m):
    cf = float(m.get("conversion_factor") or 0)
    stock = float(m.get("stock") or 0)
    avg = float(m.get("avg_price") or m.get("last_price") or 0)
    m["price_per_usage"] = round(float(m.get("last_price") or 0) / cf, 6) if cf > 0 else 0
    m["stock_in_purchase_unit"] = round(stock / cf, 4) if cf > 0 else 0
    m["stock_value"] = round(stock * (avg / cf), 2) if cf > 0 else 0
    m["is_low_stock"] = stock <= float(m.get("min_stock") or 0)
    return m


@router.get("/materials")
async def list_materials(user=Depends(current_user), q: str = "", category_id: str = "", low_stock: bool = False):
    query = Q(user["business_id"])
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"code": {"$regex": q, "$options": "i"}}]
    if category_id:
        query["category_id"] = category_id
    rows = await db.raw_materials.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    rows = [enrich_material(m) for m in rows]
    if low_stock:
        rows = [m for m in rows if m["is_low_stock"]]
    return rows


def validate_material(data):
    if not data["name"].strip():
        raise HTTPException(400, "Nama bahan wajib diisi")
    if not data["purchase_unit"] or not data["usage_unit"]:
        raise HTTPException(400, "Satuan pembelian dan satuan penggunaan wajib diisi")
    num(data["conversion_factor"], "Faktor konversi", 0, allow_equal=False)
    num(data["last_price"], "Harga beli")
    num(data["min_stock"], "Minimum stok")


@router.post("/materials")
async def create_material(body: MaterialIn, user=Depends(current_user)):
    bid = user["business_id"]
    data = body.model_dump()
    validate_material(data)
    initial = data.pop("initial_stock", None)
    if not data["code"]:
        data["code"] = await next_number(bid, "BHN")
    doc = {"id": new_id(), "business_id": bid, **data, "avg_price": data["last_price"], "stock": 0, "created_at": now_iso(), "updated_at": now_iso()}
    await db.raw_materials.insert_one(dict(doc))
    if data["last_price"] > 0:
        await db.material_price_history.insert_one({"id": new_id(), "business_id": bid, "material_id": doc["id"], "date": now_iso()[:10], "price": data["last_price"], "unit": data["purchase_unit"], "source": "manual", "created_at": now_iso()})
    if initial and float(initial) > 0:
        await post_inventory(bid, "material", doc["id"], float(initial), "adjustment", price_per_usage(doc), "initial", doc["id"], "Stok awal", user=user)
    await audit(bid, user, "create", "raw_materials", doc["id"], {"name": data["name"]})
    return enrich_material(strip(await db.raw_materials.find_one({"id": doc["id"]}, {"_id": 0})))


@router.get("/materials/{mid}")
async def get_material(mid: str, user=Depends(current_user)):
    bid = user["business_id"]
    m = await get_or_404(db.raw_materials, bid, mid, "Bahan")
    history = await db.material_price_history.find({"business_id": bid, "material_id": mid}, {"_id": 0}).sort("date", -1).to_list(500)
    ledger = await db.inventory_transactions.find({"business_id": bid, "item_type": "material", "item_id": mid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {**enrich_material(m), "price_history": history, "ledger": ledger}


@router.put("/materials/{mid}")
async def update_material(mid: str, body: MaterialIn, user=Depends(current_user)):
    bid = user["business_id"]
    old = await get_or_404(db.raw_materials, bid, mid, "Bahan")
    data = body.model_dump()
    data.pop("initial_stock", None)
    validate_material(data)
    if float(old.get("last_price") or 0) != data["last_price"]:
        await db.material_price_history.insert_one({"id": new_id(), "business_id": bid, "material_id": mid, "date": now_iso()[:10], "price": data["last_price"], "unit": data["purchase_unit"], "source": "manual", "created_at": now_iso()})
        if not old.get("stock"):
            data["avg_price"] = data["last_price"]
    await db.raw_materials.update_one({"id": mid}, {"$set": {**data, "updated_at": now_iso()}})
    await audit(bid, user, "update", "raw_materials", mid)
    return enrich_material(strip(await db.raw_materials.find_one({"id": mid}, {"_id": 0})))


@router.delete("/materials/{mid}")
async def delete_material(mid: str, user=Depends(current_user)):
    bid = user["business_id"]
    await get_or_404(db.raw_materials, bid, mid, "Bahan")
    if await db.recipe_items.find_one({"business_id": bid, "material_id": mid}):
        raise HTTPException(400, "Bahan masih digunakan dalam resep. Hapus dari resep terlebih dahulu")
    await db.raw_materials.update_one({"id": mid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(bid, user, "delete", "raw_materials", mid)
    return {"ok": True}


# ---------- Products ----------
def enrich_product(p):
    stock = float(p.get("stock") or 0)
    p["stock_value"] = round(stock * float(p.get("avg_hpp") or 0), 2)
    p["is_low_stock"] = stock <= float(p.get("min_stock") or 0)
    return p


@router.get("/products")
async def list_products(user=Depends(current_user), q: str = "", category_id: str = ""):
    query = Q(user["business_id"])
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"sku": {"$regex": q, "$options": "i"}}]
    if category_id:
        query["category_id"] = category_id
    rows = await db.products.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    recipes = await db.recipes.find(Q(user["business_id"]), {"_id": 0, "id": 1, "product_id": 1}).to_list(5000)
    counts = {}
    for r in recipes:
        counts[r["product_id"]] = counts.get(r["product_id"], 0) + 1
    for p in rows:
        enrich_product(p)
        p["recipe_count"] = counts.get(p["id"], 0)
    return rows


@router.post("/products")
async def create_product(body: ProductIn, user=Depends(current_user)):
    bid = user["business_id"]
    data = body.model_dump()
    if not data["name"].strip():
        raise HTTPException(400, "Nama produk wajib diisi")
    num(data["selling_price"], "Harga jual")
    if not data["sku"]:
        data["sku"] = await next_number(bid, "SKU")
    doc = {"id": new_id(), "business_id": bid, **data, "stock": 0, "avg_hpp": 0, "last_hpp": 0, "created_at": now_iso(), "updated_at": now_iso()}
    await db.products.insert_one(dict(doc))
    await audit(bid, user, "create", "products", doc["id"], {"name": data["name"]})
    return enrich_product(doc)


@router.get("/products/{pid}")
async def get_product(pid: str, user=Depends(current_user)):
    bid = user["business_id"]
    p = await get_or_404(db.products, bid, pid, "Produk")
    recipes = await db.recipes.find(Q(bid, product_id=pid), {"_id": 0}).to_list(100)
    ledger = await db.inventory_transactions.find({"business_id": bid, "item_type": "product", "item_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {**enrich_product(p), "recipes": recipes, "ledger": ledger}


@router.put("/products/{pid}")
async def update_product(pid: str, body: ProductIn, user=Depends(current_user)):
    bid = user["business_id"]
    await get_or_404(db.products, bid, pid, "Produk")
    data = body.model_dump()
    if not data["name"].strip():
        raise HTTPException(400, "Nama produk wajib diisi")
    num(data["selling_price"], "Harga jual")
    await db.products.update_one({"id": pid}, {"$set": {**data, "updated_at": now_iso()}})
    await audit(bid, user, "update", "products", pid)
    return enrich_product(strip(await db.products.find_one({"id": pid}, {"_id": 0})))


@router.delete("/products/{pid}")
async def delete_product(pid: str, user=Depends(current_user)):
    bid = user["business_id"]
    await get_or_404(db.products, bid, pid, "Produk")
    await db.products.update_one({"id": pid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(bid, user, "delete", "products", pid)
    return {"ok": True}
