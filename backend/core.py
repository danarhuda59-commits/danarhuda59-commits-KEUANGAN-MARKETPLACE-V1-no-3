import os, uuid, math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import jwt, bcrypt
from fastapi import HTTPException, Request, Depends
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
TZ = ZoneInfo("Asia/Jakarta")
JWT_ALG = "HS256"


def new_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today_str():
    return datetime.now(TZ).date().isoformat()


def strip(doc):
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


def Q(bid, **extra):
    return {"business_id": bid, "is_deleted": {"$ne": True}, **extra}


def num(v, name, min_value=0.0, allow_equal=True):
    try:
        f = float(v if v is not None else 0)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} harus berupa angka")
    if math.isnan(f) or math.isinf(f):
        raise HTTPException(400, f"{name} tidak valid")
    if f < min_value or (not allow_equal and f <= min_value):
        raise HTTPException(400, f"{name} tidak boleh {'negatif' if min_value == 0 and allow_equal else f'kurang dari {min_value}'}")
    return f


def safe_div(a, b):
    return a / b if b else 0.0


def date_range(start, end):
    return {"$gte": start or "0000-01-01", "$lte": end or "9999-12-31"}


# ---------- Auth ----------
def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p, h):
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except Exception:
        return False


def create_token(user_id, ttype="access", hours=24):
    payload = {"sub": user_id, "type": ttype, "exp": datetime.now(timezone.utc) + timedelta(hours=hours)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALG)


def decode_token(token):
    try:
        return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Sesi berakhir, silakan login kembali")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token tidak valid")


async def user_from_token(token):
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(401, "Tipe token salah")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User tidak ditemukan")
    return user


async def current_user(request: Request):
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        token = request.query_params.get("auth")
    if not token:
        raise HTTPException(401, "Belum login")
    return await user_from_token(token)


# ---------- Audit ----------
async def audit(bid, user, action, entity, entity_id, detail=None):
    await db.audit_logs.insert_one({
        "id": new_id(), "business_id": bid, "user_id": user.get("id"), "user_name": user.get("name"),
        "action": action, "entity": entity, "entity_id": entity_id, "detail": detail or {}, "created_at": now_iso(),
    })


# ---------- Numbering ----------
async def next_number(bid, prefix):
    ym = datetime.now(TZ).strftime("%Y%m")
    key = f"{prefix}-{ym}"
    doc = await db.counters.find_one_and_update(
        {"business_id": bid, "key": key}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return f"{key}-{doc['seq']:04d}"


# ---------- Unit conversion ----------
async def load_conversions(bid):
    rows = await db.unit_conversions.find({"business_id": bid}, {"_id": 0}).to_list(2000)
    return {(r["from_unit"], r["to_unit"]): float(r["factor"]) for r in rows}


def convert_to_usage(qty, unit, material, conversions):
    usage = material.get("usage_unit")
    if not unit or unit == usage:
        return qty
    cf = float(material.get("conversion_factor") or 0)
    if unit == material.get("purchase_unit") and cf > 0:
        return qty * cf
    f = conversions.get((unit, usage))
    if f:
        return qty * f
    f2 = conversions.get((usage, unit))
    if f2:
        return qty / f2
    raise HTTPException(400, f"Konversi satuan '{unit}' ke '{usage}' tidak ditemukan untuk bahan {material.get('name')}")


def price_per_usage(material, mode="last"):
    price = float(material.get("avg_price" if mode == "avg" else "last_price") or 0)
    cf = float(material.get("conversion_factor") or 0)
    if cf <= 0:
        raise HTTPException(400, f"Faktor konversi bahan '{material.get('name')}' harus lebih dari 0")
    return price / cf


# ---------- HPP engine ----------
EXTRA_TYPES = ("packaging", "labor", "overhead", "other")


def calc_extras(extra_costs, material_total, yield_qty, batch_multiplier=1.0):
    sums = {t: 0.0 for t in EXTRA_TYPES}
    detail = []
    for c in extra_costs or []:
        v = num(c.get("value"), f"Nilai biaya '{c.get('name', '')}'")
        method = c.get("method") or "per_batch"
        if method == "per_unit":
            amt = v * yield_qty
        elif method == "pct_material":
            amt = material_total * v / 100.0
        else:
            amt = v * batch_multiplier
        t = c.get("type") if c.get("type") in EXTRA_TYPES else "other"
        sums[t] += amt
        detail.append({**c, "type": t, "method": method, "value": v, "amount": round(amt, 4)})
    return sums, detail


def compute_hpp(items, extra_costs, yield_qty, selling_price, materials, conversions, sub_costs=None, price_mode="last", target_margin=None):
    sub_costs = sub_costs or {}
    rows, material_total = [], 0.0
    for idx, it in enumerate(items or []):
        qty = num(it.get("qty"), f"Qty bahan baris {idx + 1}")
        waste = num(it.get("waste_pct"), f"Waste bahan baris {idx + 1}")
        if it.get("sub_recipe_id"):
            sub = sub_costs.get(it["sub_recipe_id"])
            if not sub:
                raise HTTPException(400, f"Sub-resep pada baris {idx + 1} tidak ditemukan")
            unit_price, qty_base = float(sub["hpp_per_unit"] or 0), qty
            name, unit, base_price, conv = sub["name"], sub.get("yield_unit") or "unit", unit_price, 1.0
            mid = None
        else:
            m = materials.get(it.get("material_id"))
            if not m:
                raise HTTPException(400, f"Bahan pada baris {idx + 1} tidak ditemukan / belum dipilih")
            unit = it.get("unit") or m.get("usage_unit")
            if not unit:
                raise HTTPException(400, f"Bahan '{m.get('name')}' belum memiliki satuan")
            qty_base = convert_to_usage(qty, unit, m, conversions)
            unit_price = price_per_usage(m, price_mode)
            name, base_price, conv, mid = m["name"], float(m.get("last_price") or 0), float(m.get("conversion_factor") or 1), m["id"]
        cost = qty_base * unit_price * (1 + waste / 100.0)
        material_total += cost
        rows.append({
            "no": idx + 1, "material_id": mid, "sub_recipe_id": it.get("sub_recipe_id"), "material_name": name,
            "quantity": qty, "unit": unit, "qty_base": round(qty_base, 6), "base_price": base_price, "conversion_factor": conv,
            "unit_price": round(unit_price, 6), "waste_pct": waste, "cost": round(cost, 4), "sort_order": idx,
        })
    yield_qty = num(yield_qty, "Hasil produksi (yield)")
    selling_price = num(selling_price, "Harga jual")
    ex, ex_detail = calc_extras(extra_costs, material_total, yield_qty)
    total_batch = material_total + sum(ex.values())
    hpp_unit = total_batch / yield_qty if yield_qty > 0 else None
    profit = (selling_price - hpp_unit) if (hpp_unit is not None and selling_price > 0) else None
    margin = (profit / selling_price * 100) if (profit is not None and selling_price > 0) else None
    markup = (profit / hpp_unit * 100) if (profit is not None and hpp_unit and hpp_unit > 0) else None
    r = lambda v: None if v is None else round(v, 4)
    return {
        "items": rows, "item_count": len(rows), "material_total": r(material_total), "packaging_total": r(ex["packaging"]),
        "labor_total": r(ex["labor"]), "overhead_total": r(ex["overhead"]), "other_total": r(ex["other"]),
        "extra_costs": ex_detail, "total_batch": r(total_batch), "yield_qty": yield_qty, "hpp_per_unit": r(hpp_unit),
        "selling_price": selling_price, "profit_per_unit": r(profit), "margin_pct": r(margin), "markup_pct": r(markup),
        **suggest_price(hpp_unit, target_margin),
        "warning": None if yield_qty > 0 else "Hasil produksi (yield) = 0, HPP per unit tidak dapat dihitung",
    }


def suggest_price(hpp_unit, target_margin):
    """Harga saran = HPP / (1 - target margin%). Margin dihitung dari harga jual, bukan markup dari HPP."""
    if target_margin is None:
        return {}
    tm = float(target_margin)
    out = {"target_margin_pct": tm, "suggested_price": None, "suggested_price_rounded": None, "suggested_profit_per_unit": None, "suggestion_note": None}
    if hpp_unit is None:
        return out
    if tm < 0 or tm >= 100:
        out["suggestion_note"] = "Target margin harus antara 0 dan 99,99% (margin 100% tidak mungkin dicapai)"
        return out
    price = hpp_unit / (1 - tm / 100.0)
    rounded = math.ceil(price / 100.0) * 100 if price > 0 else 0
    sim = []
    for m in sorted({20.0, 30.0, 40.0, 50.0, tm}):
        p = hpp_unit / (1 - m / 100.0)
        sim.append({"margin_pct": m, "price": round(p, 4), "price_rounded": math.ceil(p / 100.0) * 100 if p > 0 else 0, "profit_per_unit": round(p - hpp_unit, 4), "is_target": m == tm})
    out.update({"suggested_price": round(price, 4), "suggested_price_rounded": rounded, "suggested_profit_per_unit": round(price - hpp_unit, 4),
                "suggestion_note": f"Rp{price:,.2f} = HPP Rp{hpp_unit:,.2f} ÷ (1 − {tm:g}%)", "price_simulation": sim})
    return out


async def load_materials(bid, ids=None):
    q = Q(bid)
    if ids is not None:
        q["id"] = {"$in": list(ids)}
    rows = await db.raw_materials.find(q, {"_id": 0}).to_list(5000)
    return {m["id"]: m for m in rows}


async def get_recipe_items(recipe_id):
    return await db.recipe_items.find({"recipe_id": recipe_id}, {"_id": 0}).sort("sort_order", 1).to_list(1000)


async def business_target_margin(bid):
    biz = await db.businesses.find_one({"id": bid}, {"_id": 0, "target_margin": 1})
    return float((biz or {}).get("target_margin") or 0)


async def recipe_cost(bid, recipe, depth=0, price_mode="last", default_margin=None):
    if depth > 6:
        raise HTTPException(400, "Nested resep terlalu dalam / melingkar (maks 6 level)")
    if default_margin is None:
        default_margin = await business_target_margin(bid)
    target_margin = recipe.get("target_margin") if recipe.get("target_margin") is not None else default_margin
    items = recipe.get("items") if recipe.get("items") is not None else await get_recipe_items(recipe["id"])
    materials = await load_materials(bid)
    conversions = await load_conversions(bid)
    sub_costs = {}
    for it in items:
        sid = it.get("sub_recipe_id")
        if sid and sid not in sub_costs:
            if sid == recipe.get("id"):
                raise HTTPException(400, "Resep tidak boleh memakai dirinya sendiri sebagai sub-resep")
            sub = await db.recipes.find_one(Q(bid, id=sid), {"_id": 0})
            if not sub:
                raise HTTPException(400, "Sub-resep tidak ditemukan")
            c = await recipe_cost(bid, sub, depth + 1, price_mode, default_margin)
            sub_costs[sid] = {"hpp_per_unit": c["hpp_per_unit"] or 0, "name": f"[Sub] {sub['name']}", "yield_unit": sub.get("yield_unit")}
    return compute_hpp(items, recipe.get("extra_costs") or [], recipe.get("yield_qty"), recipe.get("selling_price") or 0,
                       materials, conversions, sub_costs, price_mode, target_margin)


async def expand_items(bid, items, factor, depth=0):
    """Flatten nested recipes into base material requirements. Returns (flat_items, extra_costs)."""
    if depth > 6:
        raise HTTPException(400, "Nested resep terlalu dalam")
    flat, extras = [], []
    for it in items:
        if it.get("sub_recipe_id"):
            sub = await db.recipes.find_one(Q(bid, id=it["sub_recipe_id"]), {"_id": 0})
            if not sub:
                raise HTTPException(400, "Sub-resep tidak ditemukan")
            sy = float(sub.get("yield_qty") or 0)
            if sy <= 0:
                raise HTTPException(400, f"Yield sub-resep '{sub['name']}' harus lebih dari 0")
            f = factor * float(it.get("qty") or 0) * (1 + float(it.get("waste_pct") or 0) / 100) / sy
            sub_items = await get_recipe_items(sub["id"])
            si, se = await expand_items(bid, sub_items, f, depth + 1)
            flat += si
            extras += se
            for c in sub.get("extra_costs") or []:
                v = float(c.get("value") or 0)
                method = c.get("method") or "per_batch"
                if method == "per_batch":
                    amt = v * f
                elif method == "per_unit":
                    amt = v * sy * f
                else:
                    # pct_material dihitung dari biaya bahan sub-resep itu sendiri (bukan bahan resep induk)
                    sub_material_total = float((await recipe_cost(bid, sub, depth + 1))["material_total"] or 0)
                    amt = sub_material_total * f * v / 100.0
                extras.append({**c, "name": f"{c.get('name')} ({sub['name']})", "method": "per_batch", "value": amt})
        else:
            flat.append({**it, "qty": float(it.get("qty") or 0) * factor})
    return flat, extras


# ---------- Inventory & cash ledger ----------
async def post_inventory(bid, item_type, item_id, qty_delta, reason, unit_cost, ref_type, ref_id, note="", date=None, is_demo=False, user=None):
    coll = db.raw_materials if item_type == "material" else db.products
    item = await coll.find_one({"id": item_id, "business_id": bid}, {"_id": 0})
    if not item:
        raise HTTPException(400, f"{'Bahan' if item_type == 'material' else 'Produk'} tidak ditemukan")
    cur = float(item.get("stock") or 0)
    new = cur + qty_delta
    if new < -1e-9:
        raise HTTPException(400, f"Stok {item['name']} tidak cukup (tersedia {cur:g}, dibutuhkan {abs(qty_delta):g})")
    new = max(new, 0.0)
    await coll.update_one({"id": item_id}, {"$set": {"stock": new, "updated_at": now_iso()}})
    unit = item.get("usage_unit") if item_type == "material" else item.get("unit")
    tx = {
        "id": new_id(), "business_id": bid, "date": date or today_str(), "item_type": item_type, "item_id": item_id,
        "item_name": item["name"], "direction": "in" if qty_delta >= 0 else "out", "reason": reason, "qty": abs(qty_delta),
        "unit": unit, "unit_cost": round(float(unit_cost or 0), 6), "total_cost": round(abs(qty_delta) * float(unit_cost or 0), 4),
        "balance_after": new, "ref_type": ref_type, "ref_id": ref_id, "note": note or "", "is_demo": is_demo,
        "created_at": now_iso(), "created_by": (user or {}).get("id"),
    }
    await db.inventory_transactions.insert_one(dict(tx))
    return tx


async def post_cash(bid, account_id, direction, amount, category, ref_type, ref_id, description, date=None, is_demo=False):
    if not account_id:
        acc = await db.cash_accounts.find_one(Q(bid), {"_id": 0})
        if not acc:
            raise HTTPException(400, "Belum ada akun kas. Buat akun kas terlebih dahulu")
        account_id = acc["id"]
    else:
        acc = await db.cash_accounts.find_one(Q(bid, id=account_id), {"_id": 0})
        if not acc:
            raise HTTPException(400, "Akun kas tidak ditemukan")
    tx = {
        "id": new_id(), "business_id": bid, "account_id": account_id, "account_name": acc["name"], "date": date or today_str(),
        "direction": direction, "amount": round(float(amount), 2), "category": category, "ref_type": ref_type, "ref_id": ref_id,
        "description": description, "is_demo": is_demo, "created_at": now_iso(),
    }
    await db.cash_transactions.insert_one(dict(tx))
    return tx


async def reverse_ref(bid, ref_type, ref_id, user):
    """Reverse stock movements and delete cash entries for a transaction."""
    txs = await db.inventory_transactions.find({"business_id": bid, "ref_type": ref_type, "ref_id": ref_id, "reversed": {"$ne": True}}, {"_id": 0}).to_list(5000)
    for t in txs:
        delta = -t["qty"] if t["direction"] == "in" else t["qty"]
        await post_inventory(bid, t["item_type"], t["item_id"], delta, "reversal", t["unit_cost"], f"{ref_type}_reversal", ref_id, f"Pembatalan {ref_type}", user=user)
        await db.inventory_transactions.update_one({"id": t["id"]}, {"$set": {"reversed": True}})
    await db.cash_transactions.delete_many({"business_id": bid, "ref_type": ref_type, "ref_id": ref_id})
