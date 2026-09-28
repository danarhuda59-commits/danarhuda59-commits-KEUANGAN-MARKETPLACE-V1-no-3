from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Any
from pydantic import BaseModel
from core import db, Q, new_id, now_iso, strip, num, current_user, audit, compute_hpp, load_materials, load_conversions, recipe_cost, get_recipe_items, business_target_margin

router = APIRouter(tags=["recipes"])


class RecipeItemIn(BaseModel):
    material_id: Optional[str] = None
    sub_recipe_id: Optional[str] = None
    qty: float = 0
    unit: Optional[str] = None
    waste_pct: float = 0
    notes: Optional[str] = ""


class ExtraCostIn(BaseModel):
    name: str = ""
    type: str = "other"
    method: str = "per_batch"
    value: float = 0


class RecipeIn(BaseModel):
    product_id: Optional[str] = None
    name: str
    version: Optional[str] = "v1"
    yield_qty: float = 1
    yield_unit: Optional[str] = "pcs"
    selling_price: float = 0
    target_margin: Optional[float] = None
    is_default: bool = False
    is_sub_recipe: bool = False
    notes: Optional[str] = ""
    items: List[RecipeItemIn] = []
    extra_costs: List[ExtraCostIn] = []


class HppCalcIn(BaseModel):
    items: List[RecipeItemIn] = []
    extra_costs: List[ExtraCostIn] = []
    yield_qty: float = 1
    selling_price: float = 0
    target_margin: Optional[float] = None


def validate_recipe(data):
    if not data["name"].strip():
        raise HTTPException(400, "Nama resep wajib diisi")
    num(data["yield_qty"], "Hasil produksi (yield)")
    num(data["selling_price"], "Harga jual")
    if data.get("target_margin") is not None and not (0 <= float(data["target_margin"]) < 100):
        raise HTTPException(400, "Target margin harus antara 0 dan 99,99%")
    for i, it in enumerate(data["items"]):
        if not it.get("material_id") and not it.get("sub_recipe_id"):
            raise HTTPException(400, f"Bahan pada baris {i + 1} belum dipilih")
        num(it.get("qty"), f"Qty baris {i + 1}")
        num(it.get("waste_pct"), f"Waste baris {i + 1}")


async def save_items(bid, recipe_id, items):
    await db.recipe_items.delete_many({"recipe_id": recipe_id})
    if items:
        await db.recipe_items.insert_many([{"id": new_id(), "business_id": bid, "recipe_id": recipe_id, **it, "sort_order": i, "created_at": now_iso()} for i, it in enumerate(items)])


async def full_recipe(bid, recipe):
    items = await get_recipe_items(recipe["id"])
    cost = await recipe_cost(bid, {**recipe, "items": items})
    product = await db.products.find_one({"id": recipe.get("product_id")}, {"_id": 0, "name": 1, "sku": 1, "selling_price": 1}) if recipe.get("product_id") else None
    return {**recipe, "items": items, "cost": cost, "product": product}


@router.get("/recipes")
async def list_recipes(user=Depends(current_user), product_id: str = "", q: str = ""):
    bid = user["business_id"]
    query = Q(bid)
    if product_id:
        query["product_id"] = product_id
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    rows = await db.recipes.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    products = {p["id"]: p for p in await db.products.find(Q(bid), {"_id": 0, "id": 1, "name": 1, "sku": 1}).to_list(5000)}
    default_margin = await business_target_margin(bid)
    out = []
    for r in rows:
        try:
            cost = await recipe_cost(bid, r, default_margin=default_margin)
            summary = {"item_count": cost["item_count"], "material_total": cost["material_total"], "total_batch": cost["total_batch"], "hpp_per_unit": cost["hpp_per_unit"], "margin_pct": cost["margin_pct"], "profit_per_unit": cost["profit_per_unit"],
                       "target_margin_pct": cost.get("target_margin_pct"), "suggested_price": cost.get("suggested_price"), "suggested_price_rounded": cost.get("suggested_price_rounded")}
        except HTTPException as e:
            summary = {"error": e.detail}
        out.append({**r, "product": products.get(r.get("product_id")), "summary": summary})
    return out


@router.post("/recipes")
async def create_recipe(body: RecipeIn, user=Depends(current_user)):
    bid = user["business_id"]
    data = body.model_dump()
    validate_recipe(data)
    items = data.pop("items")
    if data.get("product_id") and not await db.products.find_one(Q(bid, id=data["product_id"])):
        raise HTTPException(400, "Produk tidak ditemukan")
    if not data.get("selling_price") and data.get("product_id"):
        p = await db.products.find_one({"id": data["product_id"]}, {"selling_price": 1})
        data["selling_price"] = float(p.get("selling_price") or 0) if p else 0
    doc = {"id": new_id(), "business_id": bid, **data, "created_at": now_iso(), "updated_at": now_iso()}
    await recipe_cost(bid, {**doc, "items": items})
    await db.recipes.insert_one(dict(doc))
    await save_items(bid, doc["id"], items)
    if data.get("is_default") and data.get("product_id"):
        await db.recipes.update_many({"business_id": bid, "product_id": data["product_id"], "id": {"$ne": doc["id"]}}, {"$set": {"is_default": False}})
    await audit(bid, user, "create", "recipes", doc["id"], {"name": data["name"], "items": len(items)})
    return await full_recipe(bid, doc)


@router.get("/recipes/{rid}")
async def get_recipe(rid: str, user=Depends(current_user)):
    bid = user["business_id"]
    r = await db.recipes.find_one(Q(bid, id=rid), {"_id": 0})
    if not r:
        raise HTTPException(404, "Resep tidak ditemukan")
    return await full_recipe(bid, r)


@router.put("/recipes/{rid}")
async def update_recipe(rid: str, body: RecipeIn, user=Depends(current_user)):
    bid = user["business_id"]
    r = await db.recipes.find_one(Q(bid, id=rid), {"_id": 0})
    if not r:
        raise HTTPException(404, "Resep tidak ditemukan")
    data = body.model_dump()
    validate_recipe(data)
    items = data.pop("items")
    await recipe_cost(bid, {**r, **data, "items": items})
    await db.recipes.update_one({"id": rid}, {"$set": {**data, "updated_at": now_iso()}})
    await save_items(bid, rid, items)
    if data.get("is_default") and data.get("product_id"):
        await db.recipes.update_many({"business_id": bid, "product_id": data["product_id"], "id": {"$ne": rid}}, {"$set": {"is_default": False}})
    await audit(bid, user, "update", "recipes", rid, {"items": len(items)})
    return await full_recipe(bid, {**r, **data})


@router.delete("/recipes/{rid}")
async def delete_recipe(rid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.recipes.find_one(Q(bid, id=rid)):
        raise HTTPException(404, "Resep tidak ditemukan")
    if await db.recipe_items.find_one({"business_id": bid, "sub_recipe_id": rid}):
        raise HTTPException(400, "Resep ini digunakan sebagai sub-resep di resep lain")
    await db.recipes.update_one({"id": rid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(bid, user, "delete", "recipes", rid)
    return {"ok": True}


@router.post("/hpp/calculate")
async def calculate_hpp(body: HppCalcIn, user=Depends(current_user)):
    bid = user["business_id"]
    data = body.model_dump()
    sub_costs = {}
    for it in data["items"]:
        sid = it.get("sub_recipe_id")
        if sid and sid not in sub_costs:
            sub = await db.recipes.find_one(Q(bid, id=sid), {"_id": 0})
            if not sub:
                raise HTTPException(400, "Sub-resep tidak ditemukan")
            c = await recipe_cost(bid, sub)
            sub_costs[sid] = {"hpp_per_unit": c["hpp_per_unit"] or 0, "name": f"[Sub] {sub['name']}", "yield_unit": sub.get("yield_unit")}
    tm = data["target_margin"] if data.get("target_margin") is not None else await business_target_margin(bid)
    if not (0 <= float(tm) < 100):
        raise HTTPException(400, "Target margin harus antara 0 dan 99,99%")
    return compute_hpp(data["items"], data["extra_costs"], data["yield_qty"], data["selling_price"], await load_materials(bid), await load_conversions(bid), sub_costs, target_margin=tm)


@router.get("/hpp/calculations")
async def list_calculations(user=Depends(current_user)):
    return await db.hpp_calculations.find(Q(user["business_id"]), {"_id": 0}).sort("created_at", -1).to_list(200)


class SaveCalcIn(HppCalcIn):
    name: str = ""
    product_id: Optional[str] = None
    recipe_id: Optional[str] = None


@router.post("/hpp/calculations")
async def save_calculation(body: SaveCalcIn, user=Depends(current_user)):
    bid = user["business_id"]
    result = await calculate_hpp(HppCalcIn(**body.model_dump(exclude={"name", "product_id", "recipe_id"})), user)
    if result.get("target_margin_pct") is not None and not (0 <= float(result["target_margin_pct"]) < 100):
        raise HTTPException(400, "Target margin harus antara 0 dan 99,99%")
    doc = {"id": new_id(), "business_id": bid, "name": body.name or "Perhitungan HPP", "product_id": body.product_id, "recipe_id": body.recipe_id,
           "input": body.model_dump(), "result": result, "created_at": now_iso()}
    await db.hpp_calculations.insert_one(dict(doc))
    return doc


@router.delete("/hpp/calculations/{cid}")
async def delete_calculation(cid: str, user=Depends(current_user)):
    await db.hpp_calculations.delete_one({"id": cid, "business_id": user["business_id"]})
    return {"ok": True}
