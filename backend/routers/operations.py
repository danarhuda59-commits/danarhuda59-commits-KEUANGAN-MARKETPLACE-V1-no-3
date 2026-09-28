from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from core import (db, Q, new_id, now_iso, today_str, TZ, strip, num, current_user, audit, post_inventory, post_cash, reverse_ref,
                  next_number, compute_hpp, load_materials, load_conversions, get_recipe_items, expand_items, convert_to_usage, price_per_usage, date_range)

router = APIRouter(tags=["operations"])
EXPENSE_CATEGORIES = ["Operasional", "Marketing", "Iklan", "Transportasi", "Gaji", "Sewa", "Listrik", "Air", "Internet", "Peralatan", "Administrasi", "Marketplace", "Lainnya"]
PAYMENT_METHODS = ["Tunai", "Transfer Bank", "E-Wallet", "QRIS", "Kredit/Tempo", "Marketplace"]


# ---------- Production ----------
class ProductionIn(BaseModel):
    product_id: str
    recipe_id: str
    date: Optional[str] = None
    batch_count: float = 1
    qty_produced: float
    operator: Optional[str] = ""
    notes: Optional[str] = ""


@router.get("/production")
async def list_production(user=Depends(current_user), start: str = "", end: str = "", product_id: str = ""):
    q = Q(user["business_id"], date=date_range(start, end))
    if product_id:
        q["product_id"] = product_id
    return await db.production_orders.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(2000)


@router.get("/production/{pid}")
async def get_production(pid: str, user=Depends(current_user)):
    doc = await db.production_orders.find_one(Q(user["business_id"], id=pid), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Produksi tidak ditemukan")
    doc["items"] = await db.production_items.find({"production_id": pid}, {"_id": 0}).sort("sort_order", 1).to_list(1000)
    return doc


@router.post("/production")
async def create_production(body: ProductionIn, user=Depends(current_user)):
    bid = user["business_id"]
    batch = num(body.batch_count, "Jumlah batch", 0, allow_equal=False)
    qty_out = num(body.qty_produced, "Qty produksi", 0, allow_equal=False)
    product = await db.products.find_one(Q(bid, id=body.product_id), {"_id": 0})
    recipe = await db.recipes.find_one(Q(bid, id=body.recipe_id), {"_id": 0})
    if not product or not recipe:
        raise HTTPException(400, "Produk atau resep tidak ditemukan")
    items = await get_recipe_items(recipe["id"])
    if not items:
        raise HTTPException(400, "Resep kosong, tambahkan bahan terlebih dahulu sebelum produksi")
    flat, sub_extras = await expand_items(bid, items, batch)
    extras = [{**c, "value": float(c.get("value") or 0) * batch} if (c.get("method") or "per_batch") == "per_batch" else c for c in recipe.get("extra_costs") or []] + sub_extras
    materials = await load_materials(bid)
    conversions = await load_conversions(bid)
    result = compute_hpp(flat, extras, qty_out, product.get("selling_price") or 0, materials, conversions)
    # aggregate requirement per material (base qty incl. waste) and check stock
    need = {}
    for r in result["items"]:
        need[r["material_id"]] = need.get(r["material_id"], 0) + r["qty_base"] * (1 + r["waste_pct"] / 100)
    shortages = [f"{materials[m]['name']} (tersedia {float(materials[m].get('stock') or 0):g}, butuh {q:g} {materials[m]['usage_unit']})" for m, q in need.items() if float(materials[m].get("stock") or 0) + 1e-9 < q]
    if shortages:
        raise HTTPException(400, "Stok bahan tidak cukup: " + "; ".join(shortages))
    date = body.date or today_str()
    pid = new_id()
    number = await next_number(bid, "PRD")
    for m, q in need.items():
        await post_inventory(bid, "material", m, -q, "production", price_per_usage(materials[m]), "production", pid, f"Produksi {number}", date, user=user)
    hpp_unit = result["hpp_per_unit"] or 0
    old_stock, old_avg = float(product.get("stock") or 0), float(product.get("avg_hpp") or 0)
    new_avg = ((old_stock * old_avg) + (qty_out * hpp_unit)) / (old_stock + qty_out) if (old_stock + qty_out) > 0 else hpp_unit
    await post_inventory(bid, "product", product["id"], qty_out, "production", hpp_unit, "production", pid, f"Produksi {number}", date, user=user)
    await db.products.update_one({"id": product["id"]}, {"$set": {"avg_hpp": round(new_avg, 4), "last_hpp": round(hpp_unit, 4)}})
    doc = {
        "id": pid, "business_id": bid, "number": number, "date": date, "product_id": product["id"], "product_name": product["name"],
        "recipe_id": recipe["id"], "recipe_name": recipe["name"], "batch_count": batch, "qty_produced": qty_out, "unit": product.get("unit"),
        "material_total": result["material_total"], "packaging_total": result["packaging_total"], "labor_total": result["labor_total"],
        "overhead_total": result["overhead_total"], "other_total": result["other_total"], "total_cost": result["total_batch"],
        "hpp_per_unit": round(hpp_unit, 4), "selling_price": result["selling_price"], "operator": body.operator or "", "notes": body.notes or "",
        "recipe_snapshot": {"name": recipe["name"], "yield_qty": recipe.get("yield_qty"), "extra_costs": result["extra_costs"], "items": items},
        "extra_costs": result["extra_costs"], "created_by": user["id"], "created_at": now_iso(),
    }
    await db.production_orders.insert_one(dict(doc))
    await db.production_items.insert_many([{"id": new_id(), "business_id": bid, "production_id": pid, **r} for r in result["items"]])
    await audit(bid, user, "create", "production_orders", pid, {"number": number, "qty": qty_out})
    doc["items"] = result["items"]
    return doc


@router.delete("/production/{pid}")
async def delete_production(pid: str, user=Depends(current_user)):
    bid = user["business_id"]
    doc = await db.production_orders.find_one(Q(bid, id=pid), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Produksi tidak ditemukan")
    await reverse_ref(bid, "production", pid, user)
    await db.production_orders.update_one({"id": pid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(bid, user, "delete", "production_orders", pid)
    return {"ok": True}


# ---------- Inventory ----------
class AdjustIn(BaseModel):
    item_type: str
    item_id: str
    qty: float
    direction: str = "in"
    reason: str = "adjustment"
    date: Optional[str] = None
    note: Optional[str] = ""


@router.get("/inventory/transactions")
async def list_inventory(user=Depends(current_user), item_type: str = "", item_id: str = "", start: str = "", end: str = "", reason: str = ""):
    q = {"business_id": user["business_id"], "date": date_range(start, end)}
    if item_type:
        q["item_type"] = item_type
    if item_id:
        q["item_id"] = item_id
    if reason:
        q["reason"] = reason
    return await db.inventory_transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)


@router.post("/inventory/adjust")
async def adjust_inventory(body: AdjustIn, user=Depends(current_user)):
    bid = user["business_id"]
    qty = num(body.qty, "Qty", 0, allow_equal=False)
    if body.reason not in ("adjustment", "waste", "return"):
        raise HTTPException(400, "Alasan tidak valid")
    coll = db.raw_materials if body.item_type == "material" else db.products
    item = await coll.find_one(Q(bid, id=body.item_id), {"_id": 0})
    if not item:
        raise HTTPException(404, "Item tidak ditemukan")
    cost = price_per_usage(item, "avg") if body.item_type == "material" else float(item.get("avg_hpp") or 0)
    delta = qty if body.direction == "in" else -qty
    tx = await post_inventory(bid, body.item_type, body.item_id, delta, body.reason, cost, "adjustment", new_id(), body.note, body.date, user=user)
    await audit(bid, user, "adjust", "inventory", body.item_id, {"qty": delta, "reason": body.reason})
    return tx


@router.get("/inventory/summary")
async def inventory_summary(user=Depends(current_user), start: str = "", end: str = ""):
    bid = user["business_id"]
    mats = await db.raw_materials.find(Q(bid), {"_id": 0}).to_list(5000)
    prods = await db.products.find(Q(bid), {"_id": 0}).to_list(5000)
    txs = await db.inventory_transactions.find({"business_id": bid}, {"_id": 0}).to_list(50000)
    s, e = start or "0000-01-01", end or "9999-12-31"
    out = []
    for kind, rows in (("material", mats), ("product", prods)):
        for it in rows:
            mine = [t for t in txs if t["item_type"] == kind and t["item_id"] == it["id"]]
            before = sum((t["qty"] if t["direction"] == "in" else -t["qty"]) for t in mine if t["date"] < s)
            inn = sum(t["qty"] for t in mine if s <= t["date"] <= e and t["direction"] == "in" and t["reason"] not in ("adjustment", "waste", "return", "reversal"))
            outq = sum(t["qty"] for t in mine if s <= t["date"] <= e and t["direction"] == "out" and t["reason"] not in ("adjustment", "waste", "return", "reversal"))
            adj = sum((t["qty"] if t["direction"] == "in" else -t["qty"]) for t in mine if s <= t["date"] <= e and t["reason"] in ("adjustment", "waste", "return", "reversal"))
            cf = float(it.get("conversion_factor") or 1) if kind == "material" else 1
            unit_cost = (float(it.get("avg_price") or it.get("last_price") or 0) / cf) if kind == "material" else float(it.get("avg_hpp") or 0)
            stock = float(it.get("stock") or 0)
            out.append({"item_type": kind, "item_id": it["id"], "code": it.get("code") or it.get("sku"), "name": it["name"], "unit": it.get("usage_unit") if kind == "material" else it.get("unit"),
                        "opening": round(before, 4), "in_qty": round(inn, 4), "out_qty": round(outq, 4), "adjustment": round(adj, 4), "closing": round(before + inn - outq + adj, 4),
                        "current_stock": stock, "min_stock": float(it.get("min_stock") or 0), "unit_cost": round(unit_cost, 4), "stock_value": round(stock * unit_cost, 2), "is_low_stock": stock <= float(it.get("min_stock") or 0)})
    return out


# ---------- Purchases ----------
class PurchaseItemIn(BaseModel):
    material_id: str
    qty: float
    unit: Optional[str] = None
    price: float
    discount: float = 0


class PurchaseIn(BaseModel):
    date: Optional[str] = None
    supplier_id: Optional[str] = None
    items: List[PurchaseItemIn]
    discount: float = 0
    extra_cost: float = 0
    payment_method: str = "Tunai"
    payment_status: str = "paid"
    cash_account_id: Optional[str] = None
    notes: Optional[str] = ""


@router.get("/purchases")
async def list_purchases(user=Depends(current_user), start: str = "", end: str = "", supplier_id: str = "", status: str = ""):
    q = Q(user["business_id"], date=date_range(start, end))
    if supplier_id:
        q["supplier_id"] = supplier_id
    if status:
        q["payment_status"] = status
    return await db.purchases.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(5000)


@router.post("/purchases")
async def create_purchase(body: PurchaseIn, user=Depends(current_user)):
    bid = user["business_id"]
    pid = new_id()
    number = await next_number(bid, "PO")
    doc = await apply_purchase(bid, body, user, pid, number)
    await db.purchases.insert_one(dict(doc))
    await audit(bid, user, "create", "purchases", pid, {"number": number, "total": doc["total"]})
    return doc


async def revert_purchase_effects(bid, pid, user):
    await reverse_ref(bid, "purchase", pid, user)
    hist = await db.material_price_history.find({"purchase_id": pid}, {"_id": 0, "material_id": 1}).to_list(500)
    await db.material_price_history.delete_many({"purchase_id": pid})
    for mid in {h["material_id"] for h in hist}:
        latest = await db.material_price_history.find({"business_id": bid, "material_id": mid}, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(1)
        if latest:
            await db.raw_materials.update_one({"id": mid}, {"$set": {"last_price": latest[0]["price"]}})


@router.put("/purchases/{pid}")
async def update_purchase(pid: str, body: PurchaseIn, user=Depends(current_user)):
    bid = user["business_id"]
    old = await db.purchases.find_one(Q(bid, id=pid), {"_id": 0})
    if not old:
        raise HTTPException(404, "Pembelian tidak ditemukan")
    await revert_purchase_effects(bid, pid, user)
    doc = await apply_purchase(bid, body, user, pid, old["number"])
    doc["created_at"], doc["updated_at"] = old["created_at"], now_iso()
    await db.purchases.replace_one({"id": pid}, dict(doc))
    await audit(bid, user, "update", "purchases", pid, {"number": old["number"], "total": doc["total"]})
    return doc


async def apply_purchase(bid, body: PurchaseIn, user, pid, number):
    if not body.items:
        raise HTTPException(400, "Pembelian harus memiliki minimal satu bahan")
    num(body.discount, "Diskon")
    num(body.extra_cost, "Biaya tambahan")
    materials = await load_materials(bid)
    conversions = await load_conversions(bid)
    supplier = await db.suppliers.find_one(Q(bid, id=body.supplier_id), {"_id": 0}) if body.supplier_id else None
    date = body.date or today_str()
    items, subtotal = [], 0.0
    for i, it in enumerate(body.items):
        m = materials.get(it.material_id)
        if not m:
            raise HTTPException(400, f"Bahan baris {i + 1} tidak ditemukan")
        qty = num(it.qty, f"Qty baris {i + 1}", 0, allow_equal=False)
        price = num(it.price, f"Harga baris {i + 1}")
        disc = num(it.discount, f"Diskon baris {i + 1}")
        unit = it.unit or m["purchase_unit"]
        qty_base = convert_to_usage(qty, unit, m, conversions)
        line = qty * price - disc
        subtotal += line
        items.append({"material_id": m["id"], "material_name": m["name"], "qty": qty, "unit": unit, "qty_base": round(qty_base, 6), "price": price, "discount": disc, "subtotal": round(line, 2)})
    total = subtotal - body.discount + body.extra_cost
    if total < 0:
        raise HTTPException(400, "Total pembelian tidak boleh negatif")
    for it in items:
        m = materials[it["material_id"]]
        cf = float(m.get("conversion_factor") or 1)
        # effective cost per usage unit incl. line discount, price per purchase unit
        per_usage = it["subtotal"] / it["qty_base"] if it["qty_base"] > 0 else 0
        price_purchase_unit = per_usage * cf
        old_stock, old_avg_usage = float(m.get("stock") or 0), float(m.get("avg_price") or m.get("last_price") or 0) / cf
        new_avg_usage = ((old_stock * old_avg_usage) + (it["qty_base"] * per_usage)) / (old_stock + it["qty_base"]) if (old_stock + it["qty_base"]) > 0 else per_usage
        await post_inventory(bid, "material", m["id"], it["qty_base"], "purchase", per_usage, "purchase", pid, f"Pembelian {number}", date, user=user)
        await db.raw_materials.update_one({"id": m["id"]}, {"$set": {"last_price": round(price_purchase_unit, 4), "avg_price": round(new_avg_usage * cf, 4), "updated_at": now_iso()}})
        await db.material_price_history.insert_one({"id": new_id(), "business_id": bid, "material_id": m["id"], "date": date, "price": round(price_purchase_unit, 4), "unit": m["purchase_unit"],
                                                    "qty": it["qty"], "qty_unit": it["unit"], "supplier_id": body.supplier_id, "supplier_name": supplier["name"] if supplier else "", "purchase_id": pid, "source": "purchase", "created_at": now_iso()})
    paid_amount = total if body.payment_status == "paid" else 0
    if paid_amount > 0:
        await post_cash(bid, body.cash_account_id, "out", paid_amount, "purchase", "purchase", pid, f"Pembelian {number}" + (f" - {supplier['name']}" if supplier else ""), date)
    doc = {"id": pid, "business_id": bid, "number": number, "date": date, "supplier_id": body.supplier_id, "supplier_name": supplier["name"] if supplier else "-",
           "items": items, "subtotal": round(subtotal, 2), "discount": body.discount, "extra_cost": body.extra_cost, "total": round(total, 2), "paid_amount": round(paid_amount, 2),
           "payment_method": body.payment_method, "payment_status": body.payment_status, "cash_account_id": body.cash_account_id, "notes": body.notes or "", "created_by": user["id"], "created_at": now_iso()}
    return doc


class PayIn(BaseModel):
    amount: float
    cash_account_id: Optional[str] = None
    date: Optional[str] = None


@router.post("/purchases/{pid}/pay")
async def pay_purchase(pid: str, body: PayIn, user=Depends(current_user)):
    bid = user["business_id"]
    doc = await db.purchases.find_one(Q(bid, id=pid), {"_id": 0})
    if not doc:
        raise HTTPException(404, "Pembelian tidak ditemukan")
    amt = num(body.amount, "Jumlah bayar", 0, allow_equal=False)
    remaining = doc["total"] - doc.get("paid_amount", 0)
    if amt > remaining + 0.01:
        raise HTTPException(400, f"Jumlah bayar melebihi sisa hutang ({remaining:,.0f})")
    await post_cash(bid, body.cash_account_id, "out", amt, "purchase", "purchase", pid, f"Pembayaran {doc['number']}", body.date or today_str())
    paid = doc.get("paid_amount", 0) + amt
    await db.purchases.update_one({"id": pid}, {"$set": {"paid_amount": round(paid, 2), "payment_status": "paid" if paid >= doc["total"] - 0.01 else "partial"}})
    return strip(await db.purchases.find_one({"id": pid}, {"_id": 0}))


@router.delete("/purchases/{pid}")
async def delete_purchase(pid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.purchases.find_one(Q(bid, id=pid)):
        raise HTTPException(404, "Pembelian tidak ditemukan")
    await revert_purchase_effects(bid, pid, user)
    await db.purchases.update_one({"id": pid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(bid, user, "delete", "purchases", pid)
    return {"ok": True}


# ---------- Sales ----------
class SaleItemIn(BaseModel):
    product_id: str
    qty: float
    price: float
    discount: float = 0


class SaleIn(BaseModel):
    date: Optional[str] = None
    channel: str = "Offline"
    items: List[SaleItemIn]
    discount: float = 0
    platform_fee: float = 0
    service_fee: float = 0
    other_fee: float = 0
    payment_method: str = "Tunai"
    cash_account_id: Optional[str] = None
    customer: Optional[str] = ""
    notes: Optional[str] = ""


@router.get("/sales")
async def list_sales(user=Depends(current_user), start: str = "", end: str = "", channel: str = ""):
    q = Q(user["business_id"], date=date_range(start, end))
    if channel:
        q["channel"] = channel
    return await db.sales.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(5000)


@router.post("/sales")
async def create_sale(body: SaleIn, user=Depends(current_user)):
    bid = user["business_id"]
    sid = new_id()
    number = await next_number(bid, "SL")
    doc = await apply_sale(bid, body, user, sid, number)
    await db.sales.insert_one(dict(doc))
    await audit(bid, user, "create", "sales", sid, {"number": number, "total": doc["net_total"]})
    return doc


@router.put("/sales/{sid}")
async def update_sale(sid: str, body: SaleIn, user=Depends(current_user)):
    bid = user["business_id"]
    old = await db.sales.find_one(Q(bid, id=sid), {"_id": 0})
    if not old:
        raise HTTPException(404, "Penjualan tidak ditemukan")
    await reverse_ref(bid, "sale", sid, user)
    doc = await apply_sale(bid, body, user, sid, old["number"])
    doc["created_at"], doc["updated_at"] = old["created_at"], now_iso()
    await db.sales.replace_one({"id": sid}, dict(doc))
    await audit(bid, user, "update", "sales", sid, {"number": old["number"], "total": doc["net_total"]})
    return doc


async def apply_sale(bid, body: SaleIn, user, sid, number):
    if not body.items:
        raise HTTPException(400, "Penjualan harus memiliki minimal satu produk")
    for f, n in ((body.discount, "Diskon"), (body.platform_fee, "Biaya platform"), (body.service_fee, "Biaya layanan"), (body.other_fee, "Biaya lainnya")):
        num(f, n)
    products = {p["id"]: p for p in await db.products.find(Q(bid), {"_id": 0}).to_list(5000)}
    date = body.date or today_str()
    items, gross, total_hpp = [], 0.0, 0.0
    need = {}
    for i, it in enumerate(body.items):
        p = products.get(it.product_id)
        if not p:
            raise HTTPException(400, f"Produk baris {i + 1} tidak ditemukan")
        qty = num(it.qty, f"Qty baris {i + 1}", 0, allow_equal=False)
        price = num(it.price, f"Harga baris {i + 1}")
        disc = num(it.discount, f"Diskon baris {i + 1}")
        need[p["id"]] = need.get(p["id"], 0) + qty
        hpp_unit = float(p.get("avg_hpp") or 0)
        line = qty * price - disc
        gross += line
        total_hpp += qty * hpp_unit
        items.append({"product_id": p["id"], "product_name": p["name"], "sku": p.get("sku"), "qty": qty, "unit": p.get("unit"), "price": price, "discount": disc, "subtotal": round(line, 2), "hpp_unit": round(hpp_unit, 4), "hpp_total": round(qty * hpp_unit, 2), "profit": round(line - qty * hpp_unit, 2)})
    shortages = [f"{products[k]['name']} (tersedia {float(products[k].get('stock') or 0):g}, diminta {v:g})" for k, v in need.items() if float(products[k].get("stock") or 0) + 1e-9 < v]
    if shortages:
        raise HTTPException(400, "Stok produk tidak cukup: " + "; ".join(shortages))
    total = gross - body.discount
    net = total - body.platform_fee - body.service_fee - body.other_fee
    if total < 0:
        raise HTTPException(400, "Total penjualan tidak boleh negatif")
    for it in items:
        await post_inventory(bid, "product", it["product_id"], -it["qty"], "sale", it["hpp_unit"], "sale", sid, f"Penjualan {number}", date, user=user)
    if net > 0:
        await post_cash(bid, body.cash_account_id, "in", net, "sale", "sale", sid, f"Penjualan {number} ({body.channel})", date)
    doc = {"id": sid, "business_id": bid, "number": number, "date": date, "channel": body.channel, "customer": body.customer or "", "items": items,
           "gross_total": round(gross, 2), "discount": body.discount, "total": round(total, 2), "platform_fee": body.platform_fee, "service_fee": body.service_fee, "other_fee": body.other_fee,
           "net_total": round(net, 2), "total_hpp": round(total_hpp, 2), "profit": round(net - total_hpp, 2), "qty_total": sum(i["qty"] for i in items),
           "payment_method": body.payment_method, "cash_account_id": body.cash_account_id, "notes": body.notes or "", "created_by": user["id"], "created_at": now_iso()}
    return doc


@router.delete("/sales/{sid}")
async def delete_sale(sid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.sales.find_one(Q(bid, id=sid)):
        raise HTTPException(404, "Penjualan tidak ditemukan")
    await reverse_ref(bid, "sale", sid, user)
    await db.sales.update_one({"id": sid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(bid, user, "delete", "sales", sid)
    return {"ok": True}


# ---------- Expenses ----------
class ExpenseIn(BaseModel):
    date: Optional[str] = None
    category: str = "Operasional"
    description: str
    amount: float
    payment_method: str = "Tunai"
    cash_account_id: Optional[str] = None
    receipt_url: Optional[str] = ""
    notes: Optional[str] = ""


@router.get("/expenses")
async def list_expenses(user=Depends(current_user), start: str = "", end: str = "", category: str = ""):
    q = Q(user["business_id"], date=date_range(start, end))
    if category:
        q["category"] = category
    return await db.expenses.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(5000)


@router.post("/expenses")
async def create_expense(body: ExpenseIn, user=Depends(current_user)):
    bid = user["business_id"]
    amt = num(body.amount, "Nominal", 0, allow_equal=False)
    if not body.description.strip():
        raise HTTPException(400, "Deskripsi wajib diisi")
    eid = new_id()
    date = body.date or today_str()
    await post_cash(bid, body.cash_account_id, "out", amt, "expense", "expense", eid, f"{body.category}: {body.description}", date)
    doc = {"id": eid, "business_id": bid, "number": await next_number(bid, "EXP"), **body.model_dump(), "date": date, "amount": amt, "created_by": user["id"], "created_at": now_iso()}
    await db.expenses.insert_one(dict(doc))
    await audit(bid, user, "create", "expenses", eid, {"amount": amt})
    return doc


@router.put("/expenses/{eid}")
async def update_expense(eid: str, body: ExpenseIn, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.expenses.find_one(Q(bid, id=eid)):
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    amt = num(body.amount, "Nominal", 0, allow_equal=False)
    date = body.date or today_str()
    await db.cash_transactions.delete_many({"business_id": bid, "ref_type": "expense", "ref_id": eid})
    await post_cash(bid, body.cash_account_id, "out", amt, "expense", "expense", eid, f"{body.category}: {body.description}", date)
    await db.expenses.update_one({"id": eid}, {"$set": {**body.model_dump(), "date": date, "amount": amt, "updated_at": now_iso()}})
    await audit(bid, user, "update", "expenses", eid)
    return strip(await db.expenses.find_one({"id": eid}, {"_id": 0}))


@router.delete("/expenses/{eid}")
async def delete_expense(eid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.expenses.find_one(Q(bid, id=eid)):
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    await db.cash_transactions.delete_many({"business_id": bid, "ref_type": "expense", "ref_id": eid})
    await db.expenses.update_one({"id": eid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await audit(bid, user, "delete", "expenses", eid)
    return {"ok": True}


@router.get("/alerts/stock")
async def stock_alerts(user=Depends(current_user), cover_days: int = 14):
    """Daily low-stock alert list with suggested reorder qty based on last 30 days usage."""
    bid = user["business_id"]
    from datetime import datetime, timedelta
    since = (datetime.now(TZ).date() - timedelta(days=30)).isoformat()
    txs = await db.inventory_transactions.find({"business_id": bid, "direction": "out", "reason": {"$in": ["production", "sale"]}, "date": {"$gte": since}}, {"_id": 0, "item_type": 1, "item_id": 1, "qty": 1}).to_list(100000)
    usage = {}
    for t in txs:
        usage[(t["item_type"], t["item_id"])] = usage.get((t["item_type"], t["item_id"]), 0) + t["qty"]
    out = []
    for kind, coll in (("material", db.raw_materials), ("product", db.products)):
        for it in await coll.find(Q(bid, is_active={"$ne": False}), {"_id": 0}).to_list(10000):
            stock, mn = float(it.get("stock") or 0), float(it.get("min_stock") or 0)
            if stock > mn:
                continue
            daily = usage.get((kind, it["id"]), 0) / 30.0
            target = max(mn + daily * cover_days, mn * 2)
            suggested = max(target - stock, 0)
            cf = float(it.get("conversion_factor") or 1) if kind == "material" else 1
            unit_cost = (float(it.get("avg_price") or it.get("last_price") or 0) / cf) if kind == "material" else float(it.get("avg_hpp") or 0)
            out.append({"item_type": kind, "item_id": it["id"], "name": it["name"], "code": it.get("code") or it.get("sku"), "unit": it.get("usage_unit") if kind == "material" else it.get("unit"),
                        "stock": stock, "min_stock": mn, "avg_daily_usage": round(daily, 3), "days_left": round(stock / daily, 1) if daily > 0 else None,
                        "suggested_qty": round(suggested, 2), "suggested_purchase_qty": round(suggested / cf, 3) if kind == "material" else None, "purchase_unit": it.get("purchase_unit") if kind == "material" else None,
                        "estimated_cost": round(suggested * unit_cost, 2), "severity": "critical" if stock <= 0 else "low", "action": "Beli bahan" if kind == "material" else "Produksi"})
    out.sort(key=lambda x: (x["severity"] != "critical", x["days_left"] if x["days_left"] is not None else 1e9))
    return {"date": today_str(), "count": len(out), "critical": sum(1 for x in out if x["severity"] == "critical"), "alerts": out}


@router.get("/meta")
async def meta(user=Depends(current_user)):
    channels = await db.channels.find({"business_id": user["business_id"], "is_active": {"$ne": False}}, {"_id": 0}).to_list(100)
    import storage
    return {"expense_categories": EXPENSE_CATEGORIES, "payment_methods": PAYMENT_METHODS, "channels": [c["name"] for c in channels], "storage_enabled": storage.storage_enabled(),
            "extra_cost_types": [{"value": "packaging", "label": "Kemasan"}, {"value": "labor", "label": "Tenaga Kerja Langsung"}, {"value": "overhead", "label": "Overhead Produksi"}, {"value": "other", "label": "Biaya Produksi Lainnya"}],
            "cost_methods": [{"value": "per_batch", "label": "Per Batch"}, {"value": "per_unit", "label": "Per Unit"}, {"value": "pct_material", "label": "% dari Biaya Bahan"}]}
