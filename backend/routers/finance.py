from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel
from datetime import date as ddate, timedelta
from collections import defaultdict
from core import db, Q, new_id, now_iso, today_str, strip, num, current_user, audit, post_cash, date_range, safe_div

router = APIRouter(tags=["finance"])


# ---------- Cash ----------
class AccountIn(BaseModel):
    name: str
    type: str = "cash"
    opening_balance: float = 0
    notes: Optional[str] = ""


class CashTxIn(BaseModel):
    account_id: str
    direction: str
    amount: float
    date: Optional[str] = None
    category: str = "other"
    description: str = ""
    to_account_id: Optional[str] = None


async def account_balances(bid, upto=None):
    q = {"business_id": bid}
    if upto:
        q["date"] = {"$lte": upto}
    txs = await db.cash_transactions.find(q, {"_id": 0, "account_id": 1, "direction": 1, "amount": 1}).to_list(100000)
    bal = defaultdict(float)
    for t in txs:
        bal[t["account_id"]] += t["amount"] if t["direction"] == "in" else -t["amount"]
    return bal


@router.get("/cash/accounts")
async def list_accounts(user=Depends(current_user)):
    bid = user["business_id"]
    accs = await db.cash_accounts.find(Q(bid), {"_id": 0}).to_list(100)
    bal = await account_balances(bid)
    for a in accs:
        a["balance"] = round(float(a.get("opening_balance") or 0) + bal.get(a["id"], 0), 2)
    return accs


@router.post("/cash/accounts")
async def create_account(body: AccountIn, user=Depends(current_user)):
    bid = user["business_id"]
    if not body.name.strip():
        raise HTTPException(400, "Nama akun wajib diisi")
    doc = {"id": new_id(), "business_id": bid, **body.model_dump(), "created_at": now_iso()}
    await db.cash_accounts.insert_one(dict(doc))
    await audit(bid, user, "create", "cash_accounts", doc["id"])
    return doc


@router.put("/cash/accounts/{aid}")
async def update_account(aid: str, body: AccountIn, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.cash_accounts.find_one(Q(bid, id=aid)):
        raise HTTPException(404, "Akun tidak ditemukan")
    await db.cash_accounts.update_one({"id": aid}, {"$set": body.model_dump()})
    return strip(await db.cash_accounts.find_one({"id": aid}, {"_id": 0}))


@router.delete("/cash/accounts/{aid}")
async def delete_account(aid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if await db.cash_transactions.find_one({"business_id": bid, "account_id": aid}):
        raise HTTPException(400, "Akun memiliki transaksi, tidak dapat dihapus")
    await db.cash_accounts.update_one({"id": aid, "business_id": bid}, {"$set": {"is_deleted": True}})
    return {"ok": True}


@router.get("/cash/transactions")
async def list_cash_tx(user=Depends(current_user), account_id: str = "", start: str = "", end: str = "", category: str = ""):
    q = {"business_id": user["business_id"], "date": date_range(start, end)}
    if account_id:
        q["account_id"] = account_id
    if category:
        q["category"] = category
    return await db.cash_transactions.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(10000)


@router.post("/cash/transactions")
async def create_cash_tx(body: CashTxIn, user=Depends(current_user)):
    bid = user["business_id"]
    amt = num(body.amount, "Nominal", 0, allow_equal=False)
    date = body.date or today_str()
    if body.direction == "transfer":
        if not body.to_account_id or body.to_account_id == body.account_id:
            raise HTTPException(400, "Akun tujuan transfer tidak valid")
        ref = new_id()
        await post_cash(bid, body.account_id, "out", amt, "transfer", "transfer", ref, body.description or "Transfer keluar", date)
        return await post_cash(bid, body.to_account_id, "in", amt, "transfer", "transfer", ref, body.description or "Transfer masuk", date)
    if body.direction not in ("in", "out"):
        raise HTTPException(400, "Arah transaksi tidak valid")
    tx = await post_cash(bid, body.account_id, body.direction, amt, body.category or "other", "manual", new_id(), body.description or "Transaksi manual", date)
    await audit(bid, user, "create", "cash_transactions", tx["id"], {"amount": amt})
    return tx


@router.delete("/cash/transactions/{tid}")
async def delete_cash_tx(tid: str, user=Depends(current_user)):
    tx = await db.cash_transactions.find_one({"id": tid, "business_id": user["business_id"]})
    if not tx:
        raise HTTPException(404, "Transaksi tidak ditemukan")
    if tx.get("ref_type") not in ("manual", "transfer"):
        raise HTTPException(400, "Transaksi ini berasal dari modul lain, hapus dari transaksi asalnya")
    await db.cash_transactions.delete_one({"id": tid})
    return {"ok": True}


# ---------- Aggregations ----------
async def period_data(bid, start, end):
    dr = date_range(start, end)
    sales = await db.sales.find(Q(bid, date=dr), {"_id": 0}).to_list(50000)
    expenses = await db.expenses.find(Q(bid, date=dr), {"_id": 0}).to_list(50000)
    purchases = await db.purchases.find(Q(bid, date=dr), {"_id": 0}).to_list(50000)
    return sales, expenses, purchases


def pl_summary(sales, expenses):
    omzet = sum(s["total"] for s in sales)
    net_sales = sum(s["net_total"] for s in sales)
    fees = sum(s["platform_fee"] + s["service_fee"] + s["other_fee"] for s in sales)
    hpp = sum(s["total_hpp"] for s in sales)
    gross = net_sales - hpp
    opex = sum(e["amount"] for e in expenses)
    net = gross - opex
    return {"omzet": round(omzet, 2), "sales_fees": round(fees, 2), "net_sales": round(net_sales, 2), "hpp": round(hpp, 2), "gross_profit": round(gross, 2),
            "gross_margin_pct": round(safe_div(gross, net_sales) * 100, 2), "opex": round(opex, 2), "net_profit": round(net, 2),
            "net_margin_pct": round(safe_div(net, net_sales) * 100, 2), "transactions": len(sales), "qty_sold": sum(s.get("qty_total", 0) for s in sales)}


def per_product(sales):
    agg = defaultdict(lambda: {"qty": 0.0, "omzet": 0.0, "hpp": 0.0})
    names = {}
    for s in sales:
        for it in s["items"]:
            a = agg[it["product_id"]]
            a["qty"] += it["qty"]
            a["omzet"] += it["subtotal"]
            a["hpp"] += it["hpp_total"]
            names[it["product_id"]] = (it["product_name"], it.get("sku"))
    out = []
    for pid, a in agg.items():
        profit = a["omzet"] - a["hpp"]
        out.append({"product_id": pid, "product_name": names[pid][0], "sku": names[pid][1], "qty": a["qty"], "omzet": round(a["omzet"], 2), "hpp": round(a["hpp"], 2), "profit": round(profit, 2),
                    "margin_pct": round(safe_div(profit, a["omzet"]) * 100, 2), "avg_price": round(safe_div(a["omzet"], a["qty"]), 2), "hpp_per_unit": round(safe_div(a["hpp"], a["qty"]), 2)})
    return sorted(out, key=lambda x: -x["omzet"])


def per_channel(sales):
    agg = defaultdict(lambda: {"count": 0, "qty": 0.0, "omzet": 0.0, "fees": 0.0, "net": 0.0, "hpp": 0.0})
    for s in sales:
        a = agg[s["channel"]]
        a["count"] += 1
        a["qty"] += s.get("qty_total", 0)
        a["omzet"] += s["total"]
        a["fees"] += s["platform_fee"] + s["service_fee"] + s["other_fee"]
        a["net"] += s["net_total"]
        a["hpp"] += s["total_hpp"]
    return [{"channel": c, **{k: round(v, 2) for k, v in a.items()}, "profit": round(a["net"] - a["hpp"], 2), "margin_pct": round(safe_div(a["net"] - a["hpp"], a["net"]) * 100, 2)} for c, a in agg.items()]


def daily_series(sales, expenses, purchases, start, end):
    days = defaultdict(lambda: {"omzet": 0.0, "expense": 0.0, "hpp": 0.0, "purchase": 0.0})
    for s in sales:
        days[s["date"]]["omzet"] += s["net_total"]
        days[s["date"]]["hpp"] += s["total_hpp"]
    for e in expenses:
        days[e["date"]]["expense"] += e["amount"]
    for p in purchases:
        days[p["date"]]["purchase"] += p["total"]
    if start and end:
        try:
            d0, d1 = ddate.fromisoformat(start), ddate.fromisoformat(end)
            if (d1 - d0).days <= 366:
                while d0 <= d1:
                    days[d0.isoformat()]
                    d0 += timedelta(days=1)
        except ValueError:
            pass
    return [{"date": d, **{k: round(v, 2) for k, v in v.items()}, "profit": round(v["omzet"] - v["hpp"] - v["expense"], 2)} for d, v in sorted(days.items())]


@router.get("/dashboard")
async def dashboard(user=Depends(current_user), start: str = "", end: str = ""):
    bid = user["business_id"]
    today = today_str()
    month_start = today[:8] + "01"
    sales, expenses, purchases = await period_data(bid, start, end)
    t_sales, t_exp, _ = await period_data(bid, today, today)
    m_sales, m_exp, _ = await period_data(bid, month_start, today)
    summary = pl_summary(sales, expenses)
    accs = await list_accounts(user)
    mats = await db.raw_materials.find(Q(bid), {"_id": 0}).to_list(5000)
    prods = await db.products.find(Q(bid), {"_id": 0}).to_list(5000)
    mat_value = sum(float(m.get("stock") or 0) * float(m.get("avg_price") or m.get("last_price") or 0) / float(m.get("conversion_factor") or 1) for m in mats)
    prod_value = sum(float(p.get("stock") or 0) * float(p.get("avg_hpp") or 0) for p in prods)
    low_mats = [{"id": m["id"], "name": m["name"], "stock": m.get("stock", 0), "min_stock": m.get("min_stock", 0), "unit": m.get("usage_unit")} for m in mats if float(m.get("stock") or 0) <= float(m.get("min_stock") or 0)]
    low_prods = [{"id": p["id"], "name": p["name"], "stock": p.get("stock", 0), "min_stock": p.get("min_stock", 0), "unit": p.get("unit")} for p in prods if float(p.get("stock") or 0) <= float(p.get("min_stock") or 0)]
    inv = await db.inventory_transactions.find({"business_id": bid, "date": date_range(start, end)}, {"_id": 0, "date": 1, "direction": 1, "qty": 1, "item_type": 1}).to_list(50000)
    mov = defaultdict(lambda: {"in": 0.0, "out": 0.0})
    for t in inv:
        mov[t["date"]][t["direction"]] += t["qty"]
    return {
        "today_omzet": round(sum(s["net_total"] for s in t_sales), 2), "month_omzet": round(sum(s["net_total"] for s in m_sales), 2),
        "today_expense": round(sum(e["amount"] for e in t_exp), 2), "month_expense": round(sum(e["amount"] for e in m_exp), 2),
        "period": summary, "cash_balance": round(sum(a["balance"] for a in accs), 2), "accounts": accs,
        "stock_value": round(mat_value + prod_value, 2), "material_stock_value": round(mat_value, 2), "product_stock_value": round(prod_value, 2),
        "low_stock_materials": low_mats, "low_stock_products": low_prods,
        "daily": daily_series(sales, expenses, purchases, start, end), "by_channel": per_channel(sales), "by_product": per_product(sales)[:10],
        "stock_movement": [{"date": d, **v} for d, v in sorted(mov.items())],
    }


@router.get("/dashboard/material-cost-trend")
async def material_cost_trend(user=Depends(current_user)):
    """Compare latest material price this month vs last month (from price history) + purchase spend."""
    bid = user["business_id"]
    today = ddate.fromisoformat(today_str())
    cur_start = today.replace(day=1)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    mats = await db.raw_materials.find(Q(bid), {"_id": 0}).to_list(5000)
    hist = await db.material_price_history.find({"business_id": bid}, {"_id": 0}).sort([("date", 1), ("created_at", 1)]).to_list(100000)
    by_mat = defaultdict(list)
    for h in hist:
        by_mat[h["material_id"]].append(h)
    rows = []
    for m in mats:
        hs = by_mat.get(m["id"], [])
        now_p = float(m.get("last_price") or 0)
        cutoff = (today - timedelta(days=30)).isoformat()
        prev_p = next((h["price"] for h in reversed(hs) if h["date"] <= cutoff), None)
        if prev_p is None and len(hs) >= 2 and hs[0]["date"] < hs[-1]["date"]:
            prev_p = hs[0]["price"]
        if now_p is None or prev_p is None:
            continue
        change = now_p - prev_p
        rows.append({"material_id": m["id"], "name": m["name"], "unit": m.get("purchase_unit"), "prev_price": prev_p, "current_price": now_p, "change": round(change, 2),
                     "change_pct": round(safe_div(change, prev_p) * 100, 2), "stock": m.get("stock", 0), "usage_unit": m.get("usage_unit")})
    rows.sort(key=lambda r: -abs(r["change_pct"]))
    _, _, cur_pur = await period_data(bid, cur_start.isoformat(), today.isoformat())
    _, _, prev_pur = await period_data(bid, prev_start.isoformat(), prev_end.isoformat())
    cur_spend, prev_spend = sum(p["total"] for p in cur_pur), sum(p["total"] for p in prev_pur)
    up = [r for r in rows if r["change_pct"] > 0]
    down = [r for r in rows if r["change_pct"] < 0]
    return {"period": {"current": cur_start.isoformat(), "previous": prev_start.isoformat()}, "materials": rows, "up_count": len(up), "down_count": len(down), "stable_count": len(rows) - len(up) - len(down),
            "avg_change_pct": round(sum(r["change_pct"] for r in rows) / len(rows), 2) if rows else None,
            "purchase_spend_current": round(cur_spend, 2), "purchase_spend_previous": round(prev_spend, 2), "purchase_spend_change_pct": round(safe_div(cur_spend - prev_spend, prev_spend) * 100, 2) if prev_spend else None}


@router.get("/reports/profit-loss")
async def report_pl(user=Depends(current_user), start: str = "", end: str = ""):
    sales, expenses, purchases = await period_data(user["business_id"], start, end)
    by_cat = defaultdict(float)
    for e in expenses:
        by_cat[e["category"]] += e["amount"]
    return {"summary": pl_summary(sales, expenses), "expenses_by_category": [{"category": k, "amount": round(v, 2)} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
            "by_product": per_product(sales), "by_channel": per_channel(sales), "daily": daily_series(sales, expenses, purchases, start, end)}


@router.get("/reports/cash-flow")
async def report_cash_flow(user=Depends(current_user), start: str = "", end: str = "", account_id: str = ""):
    bid = user["business_id"]
    accs = await db.cash_accounts.find(Q(bid), {"_id": 0}).to_list(100)
    if account_id:
        accs = [a for a in accs if a["id"] == account_id]
    ids = [a["id"] for a in accs]
    opening = sum(float(a.get("opening_balance") or 0) for a in accs)
    q = {"business_id": bid, "account_id": {"$in": ids}}
    txs = await db.cash_transactions.find(q, {"_id": 0}).sort([("date", 1), ("created_at", 1)]).to_list(100000)
    s = start or "0000-01-01"
    e = end or "9999-12-31"
    before = sum((t["amount"] if t["direction"] == "in" else -t["amount"]) for t in txs if t["date"] < s)
    in_period = [t for t in txs if s <= t["date"] <= e]
    inflow, outflow = defaultdict(float), defaultdict(float)
    daily = defaultdict(lambda: {"in": 0.0, "out": 0.0})
    for t in in_period:
        (inflow if t["direction"] == "in" else outflow)[t["category"]] += t["amount"]
        daily[t["date"]][t["direction"]] += t["amount"]
    tot_in, tot_out = sum(inflow.values()), sum(outflow.values())
    running = opening + before
    series = []
    for d, v in sorted(daily.items()):
        running += v["in"] - v["out"]
        series.append({"date": d, "in": round(v["in"], 2), "out": round(v["out"], 2), "balance": round(running, 2)})
    return {"opening_balance": round(opening + before, 2), "total_in": round(tot_in, 2), "total_out": round(tot_out, 2), "closing_balance": round(opening + before + tot_in - tot_out, 2),
            "inflow": [{"category": k, "amount": round(v, 2)} for k, v in inflow.items()], "outflow": [{"category": k, "amount": round(v, 2)} for k, v in outflow.items()],
            "transactions": list(reversed(in_period)), "daily": series}


@router.get("/reports/sales")
async def report_sales(user=Depends(current_user), start: str = "", end: str = "", channel: str = ""):
    sales, _, _ = await period_data(user["business_id"], start, end)
    if channel:
        sales = [s for s in sales if s["channel"] == channel]
    return {"summary": pl_summary(sales, []), "sales": sorted(sales, key=lambda s: s["date"], reverse=True), "by_product": per_product(sales), "by_channel": per_channel(sales)}


@router.get("/reports/purchases")
async def report_purchases(user=Depends(current_user), start: str = "", end: str = "", supplier_id: str = ""):
    _, _, purchases = await period_data(user["business_id"], start, end)
    if supplier_id:
        purchases = [p for p in purchases if p.get("supplier_id") == supplier_id]
    by_sup, by_mat = defaultdict(lambda: {"count": 0, "total": 0.0, "paid": 0.0}), defaultdict(lambda: {"qty": 0.0, "total": 0.0, "unit": ""})
    for p in purchases:
        a = by_sup[p.get("supplier_name") or "-"]
        a["count"] += 1
        a["total"] += p["total"]
        a["paid"] += p.get("paid_amount", 0)
        for it in p["items"]:
            b = by_mat[it["material_name"]]
            b["qty"] += it["qty"]
            b["total"] += it["subtotal"]
            b["unit"] = it["unit"]
    return {"total": round(sum(p["total"] for p in purchases), 2), "count": len(purchases), "unpaid": round(sum(p["total"] - p.get("paid_amount", 0) for p in purchases), 2),
            "purchases": sorted(purchases, key=lambda p: p["date"], reverse=True),
            "by_supplier": [{"supplier": k, **{kk: round(vv, 2) for kk, vv in v.items()}, "unpaid": round(v["total"] - v["paid"], 2)} for k, v in by_sup.items()],
            "by_material": [{"material": k, "qty": v["qty"], "unit": v["unit"], "total": round(v["total"], 2), "avg_price": round(safe_div(v["total"], v["qty"]), 2)} for k, v in by_mat.items()]}


@router.get("/reports/expenses")
async def report_expenses(user=Depends(current_user), start: str = "", end: str = "", category: str = ""):
    _, expenses, _ = await period_data(user["business_id"], start, end)
    if category:
        expenses = [e for e in expenses if e["category"] == category]
    by_cat = defaultdict(float)
    for e in expenses:
        by_cat[e["category"]] += e["amount"]
    return {"total": round(sum(e["amount"] for e in expenses), 2), "count": len(expenses), "expenses": sorted(expenses, key=lambda e: e["date"], reverse=True),
            "by_category": [{"category": k, "amount": round(v, 2)} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])]}


@router.get("/reports/production")
async def report_production(user=Depends(current_user), start: str = "", end: str = "", product_id: str = ""):
    q = Q(user["business_id"], date=date_range(start, end))
    if product_id:
        q["product_id"] = product_id
    rows = await db.production_orders.find(q, {"_id": 0}).sort("date", -1).to_list(5000)
    by_prod = defaultdict(lambda: {"count": 0, "qty": 0.0, "cost": 0.0})
    for r in rows:
        a = by_prod[r["product_name"]]
        a["count"] += 1
        a["qty"] += r["qty_produced"]
        a["cost"] += r["total_cost"]
    return {"count": len(rows), "total_qty": sum(r["qty_produced"] for r in rows), "total_cost": round(sum(r["total_cost"] for r in rows), 2), "production": rows,
            "by_product": [{"product": k, **v, "cost": round(v["cost"], 2), "avg_hpp": round(safe_div(v["cost"], v["qty"]), 2)} for k, v in by_prod.items()]}


@router.get("/reports/hpp")
async def report_hpp(user=Depends(current_user), start: str = "", end: str = ""):
    bid = user["business_id"]
    from core import recipe_cost
    recipes = await db.recipes.find(Q(bid), {"_id": 0}).to_list(2000)
    products = {p["id"]: p for p in await db.products.find(Q(bid), {"_id": 0}).to_list(5000)}
    current = []
    for r in recipes:
        try:
            c = await recipe_cost(bid, r)
            p = products.get(r.get("product_id"), {})
            current.append({"recipe_id": r["id"], "recipe_name": r["name"], "product_name": p.get("name", "-"), "item_count": c["item_count"], "material_total": c["material_total"],
                            "total_batch": c["total_batch"], "yield_qty": c["yield_qty"], "hpp_per_unit": c["hpp_per_unit"], "selling_price": c["selling_price"], "margin_pct": c["margin_pct"], "markup_pct": c["markup_pct"]})
        except HTTPException as e:
            current.append({"recipe_id": r["id"], "recipe_name": r["name"], "error": e.detail})
    history = await db.production_orders.find(Q(bid, date=date_range(start, end)), {"_id": 0, "items": 0, "recipe_snapshot": 0}).sort("date", -1).to_list(5000)
    return {"current": current, "history": history}


@router.get("/reports/suppliers")
async def report_suppliers(user=Depends(current_user), start: str = "", end: str = ""):
    bid = user["business_id"]
    sups = await db.suppliers.find(Q(bid), {"_id": 0}).to_list(2000)
    _, _, purchases = await period_data(bid, start, end)
    out = []
    for s in sups:
        mine = [p for p in purchases if p.get("supplier_id") == s["id"]]
        out.append({**s, "purchase_count": len(mine), "total": round(sum(p["total"] for p in mine), 2), "unpaid": round(sum(p["total"] - p.get("paid_amount", 0) for p in mine), 2), "last_date": max([p["date"] for p in mine], default="-")})
    return out


@router.get("/reports/products")
async def report_products(user=Depends(current_user), start: str = "", end: str = ""):
    bid = user["business_id"]
    prods = await db.products.find(Q(bid), {"_id": 0}).to_list(5000)
    sales, _, _ = await period_data(bid, start, end)
    pp = {p["product_id"]: p for p in per_product(sales)}
    return [{**p, "stock_value": round(float(p.get("stock") or 0) * float(p.get("avg_hpp") or 0), 2), "sold_qty": pp.get(p["id"], {}).get("qty", 0), "omzet": pp.get(p["id"], {}).get("omzet", 0),
             "hpp_sold": pp.get(p["id"], {}).get("hpp", 0), "profit": pp.get(p["id"], {}).get("profit", 0), "margin_pct": pp.get(p["id"], {}).get("margin_pct", 0),
             "current_margin_pct": round(safe_div(float(p.get("selling_price") or 0) - float(p.get("avg_hpp") or 0), float(p.get("selling_price") or 0)) * 100, 2)} for p in prods]


@router.get("/reports/channels")
async def report_channels(user=Depends(current_user), start: str = "", end: str = ""):
    sales, _, _ = await period_data(user["business_id"], start, end)
    return per_channel(sales)


@router.get("/reports/price-history")
async def report_price_history(user=Depends(current_user), material_id: str = "", start: str = "", end: str = ""):
    q = {"business_id": user["business_id"], "date": date_range(start, end)}
    if material_id:
        q["material_id"] = material_id
    rows = await db.material_price_history.find(q, {"_id": 0}).sort("date", -1).to_list(5000)
    mats = {m["id"]: m["name"] for m in await db.raw_materials.find({"business_id": user["business_id"]}, {"_id": 0, "id": 1, "name": 1}).to_list(5000)}
    for r in rows:
        r["material_name"] = mats.get(r["material_id"], "-")
    return rows


# ---------- BEP ----------
class BepIn(BaseModel):
    name: str = ""
    product_id: Optional[str] = None
    fixed_cost: float
    selling_price: float
    variable_cost: float


def bep_calc(fixed, price, var):
    contrib = price - var
    if contrib <= 0:
        return {"error": "Harga jual harus lebih besar dari biaya variabel per unit", "bep_units": None, "bep_rupiah": None, "contribution_margin": round(contrib, 2)}
    units = fixed / contrib
    return {"bep_units": round(units, 2), "bep_rupiah": round(units * price, 2), "contribution_margin": round(contrib, 2), "contribution_margin_pct": round(contrib / price * 100, 2) if price else 0}


@router.post("/bep/calculate")
async def calc_bep(body: BepIn, user=Depends(current_user)):
    return bep_calc(num(body.fixed_cost, "Fixed cost"), num(body.selling_price, "Harga jual"), num(body.variable_cost, "Variable cost"))


@router.get("/bep")
async def list_bep(user=Depends(current_user)):
    return await db.bep_calculations.find(Q(user["business_id"]), {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/bep")
async def save_bep(body: BepIn, user=Depends(current_user)):
    res = bep_calc(num(body.fixed_cost, "Fixed cost"), num(body.selling_price, "Harga jual"), num(body.variable_cost, "Variable cost"))
    doc = {"id": new_id(), "business_id": user["business_id"], **body.model_dump(), "result": res, "created_at": now_iso()}
    await db.bep_calculations.insert_one(dict(doc))
    return doc


@router.delete("/bep/{bid_}")
async def delete_bep(bid_: str, user=Depends(current_user)):
    await db.bep_calculations.delete_one({"id": bid_, "business_id": user["business_id"]})
    return {"ok": True}


@router.get("/audit-logs")
async def audit_logs(user=Depends(current_user), limit: int = 200):
    return await db.audit_logs.find({"business_id": user["business_id"]}, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
