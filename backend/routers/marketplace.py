import io, re
from collections import defaultdict
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import pandas as pd
from core import db, Q, new_id, now_iso, today_str, strip, num, safe_div, current_user, audit, post_inventory, post_cash, reverse_ref, date_range

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

CHANNELS = ["Shopee", "TikTok Shop", "Tokopedia", "Website"]
STATUSES = ["Pending", "Diproses", "Dikirim", "Selesai", "Dibatalkan", "Dikembalikan", "Refund"]
STOCK_STATUSES = {"Diproses", "Dikirim", "Selesai"}
REFUND_STATUSES = {"Dikembalikan", "Refund"}
FEE_CATEGORIES = {"admin": "admin_fee", "service": "service_fee", "transaction": "transaction_fee", "other": "other_marketplace_fee"}
FEE_FIELDS = list(FEE_CATEGORIES.values())
R = lambda v: round(float(v or 0), 2)


def check_channel(ch):
    if ch not in CHANNELS:
        raise HTTPException(400, f"Channel harus salah satu dari: {', '.join(CHANNELS)}")


# ---------- H. Pengaturan Biaya Channel ----------
class FeeIn(BaseModel):
    name: str
    channel: str
    category: str = "admin"
    fee_type: str = "percent"
    value: float = 0
    valid_from: Optional[str] = ""
    valid_to: Optional[str] = ""
    is_active: bool = True
    notes: Optional[str] = ""


def validate_fee(body: FeeIn):
    check_channel(body.channel)
    if body.category not in FEE_CATEGORIES:
        raise HTTPException(400, "Kategori biaya tidak valid")
    if body.fee_type not in ("percent", "nominal"):
        raise HTTPException(400, "Tipe biaya harus percent atau nominal")
    v = num(body.value, "Nilai biaya")
    if body.fee_type == "percent" and v > 100:
        raise HTTPException(400, "Persentase biaya tidak boleh lebih dari 100%")
    if not body.name.strip():
        raise HTTPException(400, "Nama biaya wajib diisi")
    return {**body.model_dump(), "value": v}


@router.get("/fees")
async def list_fees(user=Depends(current_user), channel: str = ""):
    q = Q(user["business_id"])
    if channel:
        q["channel"] = channel
    return await db.sales_fees.find(q, {"_id": 0}).sort([("channel", 1), ("name", 1)]).to_list(1000)


@router.post("/fees")
async def create_fee(body: FeeIn, user=Depends(current_user)):
    bid = user["business_id"]
    doc = {"id": new_id(), "business_id": bid, **validate_fee(body), "created_at": now_iso(), "updated_at": now_iso()}
    await db.sales_fees.insert_one(dict(doc))
    await audit(bid, user, "create", "sales_fees", doc["id"], {"name": body.name})
    return doc


@router.put("/fees/{fid}")
async def update_fee(fid: str, body: FeeIn, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.sales_fees.find_one(Q(bid, id=fid)):
        raise HTTPException(404, "Biaya tidak ditemukan")
    await db.sales_fees.update_one({"id": fid}, {"$set": {**validate_fee(body), "updated_at": now_iso()}})
    await audit(bid, user, "update", "sales_fees", fid)
    return strip(await db.sales_fees.find_one({"id": fid}, {"_id": 0}))


@router.delete("/fees/{fid}")
async def delete_fee(fid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.sales_fees.find_one(Q(bid, id=fid)):
        raise HTTPException(404, "Biaya tidak ditemukan")
    await db.sales_fees.update_one({"id": fid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    return {"ok": True}


async def compute_channel_fees(bid, channel, date, base):
    """Biaya marketplace otomatis dari pengaturan aktif yang berlaku pada tanggal pesanan."""
    rows = await db.sales_fees.find(Q(bid, channel=channel, is_active=True), {"_id": 0}).to_list(500)
    out = {f: 0.0 for f in FEE_FIELDS}
    detail = []
    for r in rows:
        if (r.get("valid_from") and date < r["valid_from"]) or (r.get("valid_to") and date > r["valid_to"]):
            continue
        amt = base * float(r["value"]) / 100.0 if r["fee_type"] == "percent" else float(r["value"])
        field = FEE_CATEGORIES.get(r.get("category"), "other_marketplace_fee")
        out[field] += amt
        detail.append({"fee_id": r["id"], "name": r["name"], "category": r.get("category"), "fee_type": r["fee_type"], "value": r["value"], "amount": R(amt)})
    return {k: R(v) for k, v in out.items()}, detail


@router.get("/fees/preview")
async def preview_fees(user=Depends(current_user), channel: str = "", date: str = "", base: float = 0):
    check_channel(channel)
    fees, detail = await compute_channel_fees(user["business_id"], channel, date or today_str(), num(base, "Dasar perhitungan"))
    return {"fees": fees, "detail": detail, "total": R(sum(fees.values()))}


# ---------- D. Biaya Beban Packaging ----------
class PackagingItemIn(BaseModel):
    name: str
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = ""
    purchase_price: float = 0
    purchase_qty: float = 1
    unit: str = "pcs"
    date: Optional[str] = None
    notes: Optional[str] = ""


def item_doc(body: PackagingItemIn):
    if not body.name.strip():
        raise HTTPException(400, "Nama komponen wajib diisi")
    price = num(body.purchase_price, "Harga beli")
    qty = num(body.purchase_qty, "Qty/isi pembelian", 0, allow_equal=False)
    return {**body.model_dump(), "purchase_price": price, "purchase_qty": qty, "unit_price": round(price / qty, 4), "date": body.date or today_str()}


@router.get("/packaging/items")
async def list_packaging_items(user=Depends(current_user)):
    return await db.packaging_items.find(Q(user["business_id"]), {"_id": 0}).sort("name", 1).to_list(2000)


@router.post("/packaging/items")
async def create_packaging_item(body: PackagingItemIn, user=Depends(current_user)):
    bid = user["business_id"]
    doc = {"id": new_id(), "business_id": bid, **item_doc(body), "created_at": now_iso(), "updated_at": now_iso()}
    await db.packaging_items.insert_one(dict(doc))
    await audit(bid, user, "create", "packaging_items", doc["id"], {"name": body.name})
    return doc


async def recalc_configs_using(bid, item_id):
    """Harga komponen berubah → biaya konfigurasi yang memakainya ikut diperbarui."""
    items = {i["id"]: i for i in await db.packaging_items.find(Q(bid), {"_id": 0}).to_list(2000)}
    async for cfg in db.packaging_costs.find(Q(bid, **{"components.item_id": item_id}), {"_id": 0}):
        comps = [build_component(c, items) for c in cfg["components"]]
        await db.packaging_costs.update_one({"id": cfg["id"]}, {"$set": {"components": comps, "cost_per_product": R(sum(c["cost"] for c in comps)), "updated_at": now_iso()}})


@router.put("/packaging/items/{iid}")
async def update_packaging_item(iid: str, body: PackagingItemIn, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.packaging_items.find_one(Q(bid, id=iid)):
        raise HTTPException(404, "Komponen tidak ditemukan")
    await db.packaging_items.update_one({"id": iid}, {"$set": {**item_doc(body), "updated_at": now_iso()}})
    await recalc_configs_using(bid, iid)
    return strip(await db.packaging_items.find_one({"id": iid}, {"_id": 0}))


@router.delete("/packaging/items/{iid}")
async def delete_packaging_item(iid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if await db.packaging_costs.find_one(Q(bid, **{"components.item_id": iid})):
        raise HTTPException(400, "Komponen masih dipakai oleh konfigurasi packaging")
    await db.packaging_items.update_one({"id": iid, "business_id": bid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    return {"ok": True}


class ComponentIn(BaseModel):
    item_id: str
    qty: float = 1


class PackagingCostIn(BaseModel):
    name: str
    components: List[ComponentIn]
    notes: Optional[str] = ""
    is_active: bool = True


def build_component(c, items):
    it = items.get(c["item_id"] if isinstance(c, dict) else c.item_id)
    if not it:
        raise HTTPException(400, "Komponen packaging tidak ditemukan")
    qty = num(c["qty"] if isinstance(c, dict) else c.qty, f"Qty penggunaan {it['name']}", 0, allow_equal=False)
    return {"item_id": it["id"], "item_name": it["name"], "unit": it["unit"], "qty": qty, "unit_price": it["unit_price"], "cost": round(qty * it["unit_price"], 4)}


async def config_doc(bid, body: PackagingCostIn):
    if not body.name.strip():
        raise HTTPException(400, "Nama packaging wajib diisi")
    if not body.components:
        raise HTTPException(400, "Minimal satu komponen packaging")
    items = {i["id"]: i for i in await db.packaging_items.find(Q(bid), {"_id": 0}).to_list(2000)}
    comps = [build_component(c, items) for c in body.components]
    return {"name": body.name.strip(), "notes": body.notes or "", "is_active": body.is_active, "components": comps, "cost_per_product": R(sum(c["cost"] for c in comps))}


@router.get("/packaging/configs")
async def list_packaging_configs(user=Depends(current_user)):
    bid = user["business_id"]
    cfgs = await db.packaging_costs.find(Q(bid), {"_id": 0}).sort("name", 1).to_list(1000)
    prods = await db.products.find(Q(bid, packaging_cost_id={"$ne": None}), {"_id": 0, "id": 1, "name": 1, "sku": 1, "packaging_cost_id": 1}).to_list(5000)
    by_cfg = defaultdict(list)
    for p in prods:
        by_cfg[p["packaging_cost_id"]].append({"id": p["id"], "name": p["name"], "sku": p.get("sku")})
    for c in cfgs:
        c["products"] = by_cfg.get(c["id"], [])
    return cfgs


@router.post("/packaging/configs")
async def create_packaging_config(body: PackagingCostIn, user=Depends(current_user)):
    bid = user["business_id"]
    doc = {"id": new_id(), "business_id": bid, **(await config_doc(bid, body)), "created_at": now_iso(), "updated_at": now_iso()}
    await db.packaging_costs.insert_one(dict(doc))
    await audit(bid, user, "create", "packaging_costs", doc["id"], {"name": body.name})
    return doc


@router.put("/packaging/configs/{cid}")
async def update_packaging_config(cid: str, body: PackagingCostIn, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.packaging_costs.find_one(Q(bid, id=cid)):
        raise HTTPException(404, "Konfigurasi packaging tidak ditemukan")
    await db.packaging_costs.update_one({"id": cid}, {"$set": {**(await config_doc(bid, body)), "updated_at": now_iso()}})
    return strip(await db.packaging_costs.find_one({"id": cid}, {"_id": 0}))


@router.delete("/packaging/configs/{cid}")
async def delete_packaging_config(cid: str, user=Depends(current_user)):
    bid = user["business_id"]
    await db.packaging_costs.update_one({"id": cid, "business_id": bid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    await db.products.update_many({"business_id": bid, "packaging_cost_id": cid}, {"$set": {"packaging_cost_id": None}})
    return {"ok": True}


class AssignIn(BaseModel):
    product_id: str
    packaging_cost_id: Optional[str] = None


@router.put("/packaging/assign")
async def assign_packaging(body: AssignIn, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.products.find_one(Q(bid, id=body.product_id)):
        raise HTTPException(404, "Produk tidak ditemukan")
    if body.packaging_cost_id and not await db.packaging_costs.find_one(Q(bid, id=body.packaging_cost_id)):
        raise HTTPException(404, "Konfigurasi packaging tidak ditemukan")
    await db.products.update_one({"id": body.product_id}, {"$set": {"packaging_cost_id": body.packaging_cost_id or None, "updated_at": now_iso()}})
    await audit(bid, user, "assign_packaging", "products", body.product_id, {"packaging_cost_id": body.packaging_cost_id})
    return {"ok": True}


async def product_packaging_cost(bid, product):
    cid = product.get("packaging_cost_id")
    if not cid:
        return 0.0, None
    cfg = await db.packaging_costs.find_one(Q(bid, id=cid), {"_id": 0})
    return (float(cfg["cost_per_product"]), cfg["name"]) if cfg else (0.0, None)


# ---------- B/C. Order marketplace ----------
class OrderIn(BaseModel):
    order_id: str
    date: Optional[str] = None
    channel: str
    customer: Optional[str] = ""
    product_id: str
    qty: float = 1
    normal_price: Optional[float] = None
    selling_price: float
    discount: float = 0
    voucher: float = 0
    shipping_fee: float = 0
    shipping_subsidy: float = 0
    admin_fee: Optional[float] = None
    service_fee: Optional[float] = None
    transaction_fee: Optional[float] = None
    other_marketplace_fee: Optional[float] = None
    ad_fee: float = 0
    other_operational_fee: float = 0
    refund: float = 0
    packaging_cost_per_unit: Optional[float] = None
    status: str = "Pending"
    notes: Optional[str] = ""
    source: str = "manual"


def calc_order(gross_unit, qty, discount, voucher, refund, hpp_unit, pack_unit, fees, ad_fee, other_op, shipping_fee):
    """Rumus spesifikasi C. Semua komponen terpisah, tidak ada yang dihitung dua kali."""
    gross = gross_unit * qty
    net = gross - discount - voucher - refund
    hpp = hpp_unit * qty
    packaging = pack_unit * qty
    total_cost = hpp + packaging
    gross_profit = net - hpp - packaging
    mp_fees = sum(fees.values())
    net_profit = gross_profit - mp_fees - ad_fee - other_op
    margin = safe_div(net_profit, net) * 100 if net > 0 else 0.0
    return {
        "gross_revenue": R(gross), "net_revenue": R(net), "hpp_unit": round(hpp_unit, 4), "hpp_total": R(hpp), "packaging_cost_per_unit": round(pack_unit, 4), "packaging_cost": R(packaging),
        "total_cost": R(total_cost), "gross_profit": R(gross_profit), "marketplace_fee_total": R(mp_fees), "net_profit": R(net_profit), "margin_pct": round(margin, 2),
        "customer_paid": R(gross - discount - voucher + shipping_fee), "seller_received": R(net - mp_fees - ad_fee),
    }


async def build_order(bid, body: OrderIn, user, oid, existing=None):
    check_channel(body.channel)
    if body.status not in STATUSES:
        raise HTTPException(400, f"Status harus salah satu dari: {', '.join(STATUSES)}")
    if not body.order_id.strip():
        raise HTTPException(400, "Order ID wajib diisi")
    product = await db.products.find_one(Q(bid, id=body.product_id), {"_id": 0})
    if not product:
        raise HTTPException(400, "Produk tidak ditemukan")
    qty = num(body.qty, "Qty", 0, allow_equal=False)
    price = num(body.selling_price, "Harga jual")
    discount, voucher, refund = num(body.discount, "Diskon"), num(body.voucher, "Voucher"), num(body.refund, "Refund")
    ad_fee, other_op = num(body.ad_fee, "Biaya iklan"), num(body.other_operational_fee, "Biaya operasional lain")
    ship, subsidy = num(body.shipping_fee, "Ongkir"), num(body.shipping_subsidy, "Subsidi ongkir")
    date = body.date or today_str()
    if body.status in REFUND_STATUSES and refund <= 0:
        refund = max(price * qty - discount - voucher, 0)
    manual = {f: getattr(body, f) for f in FEE_FIELDS}
    fee_detail = []
    if all(v is None for v in manual.values()):
        fees, fee_detail = await compute_channel_fees(bid, body.channel, date, max(price * qty - discount - voucher, 0))
        fee_source = "auto"
    else:
        fees = {f: num(manual[f] or 0, f) for f in FEE_FIELDS}
        fee_source = "manual"
    if body.packaging_cost_per_unit is not None:
        pack_unit, pack_name = num(body.packaging_cost_per_unit, "Biaya packaging per produk"), "manual"
    else:
        pack_unit, pack_name = await product_packaging_cost(bid, product)
    hpp_unit = float(existing["hpp_unit"]) if existing and existing.get("stock_deducted") else float(product.get("avg_hpp") or 0)
    calc = calc_order(price, qty, discount, voucher, refund, hpp_unit, pack_unit, fees, ad_fee, other_op, ship)
    return {
        "id": oid, "business_id": bid, "order_id": body.order_id.strip(), "date": date, "channel": body.channel, "customer": body.customer or "",
        "product_id": product["id"], "product_name": product["name"], "sku": product.get("sku") or "", "unit": product.get("unit"), "qty": qty,
        "normal_price": num(body.normal_price, "Harga normal") if body.normal_price is not None else price, "selling_price": price,
        "discount": discount, "voucher": voucher, "shipping_fee": ship, "shipping_subsidy": subsidy, **fees, "fee_source": fee_source, "fee_detail": fee_detail,
        "ad_fee": ad_fee, "other_operational_fee": other_op, "refund": refund, "packaging_name": pack_name, **calc,
        "status": body.status, "notes": body.notes or "", "source": body.source or "manual",
        "stock_deducted": bool(existing and existing.get("stock_deducted")), "stock_warning": None,
        "created_by": user["id"], "created_at": existing["created_at"] if existing else now_iso(), "updated_at": now_iso(),
    }


async def sync_stock(bid, doc, user):
    """Satu titik pengurangan stok: dikurangi sekali saat status masuk Diproses/Dikirim/Selesai, dikembalikan saat keluar dari status itu."""
    should = doc["status"] in STOCK_STATUSES
    if should and not doc["stock_deducted"]:
        try:
            await post_inventory(bid, "product", doc["product_id"], -doc["qty"], "sale", doc["hpp_unit"], "sales_order", doc["id"], f"Order {doc['channel']} {doc['order_id']}", doc["date"], user=user)
            doc["stock_deducted"], doc["stock_warning"] = True, None
        except HTTPException as e:
            doc["stock_warning"] = e.detail
    elif not should and doc["stock_deducted"]:
        await reverse_ref(bid, "sales_order", doc["id"], user)
        doc["stock_deducted"] = False
    return doc


async def find_duplicate(bid, order_id, sku, exclude_id=None):
    q = Q(bid, order_id=order_id, sku=sku or "")
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    return await db.sales_orders.find_one(q, {"_id": 0, "id": 1})


@router.get("/orders")
async def list_orders(user=Depends(current_user), start: str = "", end: str = "", channel: str = "", product_id: str = "", sku: str = "", status: str = "", q: str = ""):
    query = Q(user["business_id"], date=date_range(start, end))
    for k, v in (("channel", channel), ("product_id", product_id), ("sku", sku), ("status", status)):
        if v:
            query[k] = v
    if q:
        query["$or"] = [{"order_id": {"$regex": re.escape(q), "$options": "i"}}, {"customer": {"$regex": re.escape(q), "$options": "i"}}, {"product_name": {"$regex": re.escape(q), "$options": "i"}}]
    return await db.sales_orders.find(query, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(10000)


@router.post("/orders/preview")
async def preview_order(body: OrderIn, user=Depends(current_user)):
    return await build_order(user["business_id"], body, user, "preview")


@router.post("/orders")
async def create_order(body: OrderIn, user=Depends(current_user)):
    bid = user["business_id"]
    doc = await build_order(bid, body, user, new_id())
    if await find_duplicate(bid, doc["order_id"], doc["sku"]):
        raise HTTPException(400, f"Order ID {doc['order_id']} dengan SKU {doc['sku'] or '-'} sudah ada (duplikat)")
    doc = await sync_stock(bid, doc, user)
    await db.sales_orders.insert_one(dict(doc))
    await audit(bid, user, "create", "sales_orders", doc["id"], {"order_id": doc["order_id"], "net_profit": doc["net_profit"]})
    return doc


@router.put("/orders/{oid}")
async def update_order(oid: str, body: OrderIn, user=Depends(current_user)):
    bid = user["business_id"]
    old = await db.sales_orders.find_one(Q(bid, id=oid), {"_id": 0})
    if not old:
        raise HTTPException(404, "Order tidak ditemukan")
    doc = await build_order(bid, body, user, oid, old)
    if await find_duplicate(bid, doc["order_id"], doc["sku"], oid):
        raise HTTPException(400, "Order ID + SKU sudah dipakai order lain")
    if old["stock_deducted"] and (old["product_id"] != doc["product_id"] or abs(old["qty"] - doc["qty"]) > 1e-9):
        await reverse_ref(bid, "sales_order", oid, user)
        doc["stock_deducted"] = False
    doc = await sync_stock(bid, doc, user)
    await db.sales_orders.replace_one({"id": oid}, dict(doc))
    await audit(bid, user, "update", "sales_orders", oid, {"order_id": doc["order_id"]})
    return doc


class StatusIn(BaseModel):
    status: str


@router.patch("/orders/{oid}/status")
async def set_status(oid: str, body: StatusIn, user=Depends(current_user)):
    bid = user["business_id"]
    old = await db.sales_orders.find_one(Q(bid, id=oid), {"_id": 0})
    if not old:
        raise HTTPException(404, "Order tidak ditemukan")
    data = {k: old.get(k) for k in OrderIn.model_fields if k in old}
    data["status"] = body.status
    payload = OrderIn(**data)
    if old.get("fee_source") == "auto":
        for f in FEE_FIELDS:
            setattr(payload, f, None)
    if old.get("packaging_name") != "manual":
        payload.packaging_cost_per_unit = None
    return await update_order(oid, payload, user)


@router.delete("/orders/{oid}")
async def delete_order(oid: str, user=Depends(current_user)):
    bid = user["business_id"]
    old = await db.sales_orders.find_one(Q(bid, id=oid), {"_id": 0})
    if not old:
        raise HTTPException(404, "Order tidak ditemukan")
    if old.get("stock_deducted"):
        await reverse_ref(bid, "sales_order", oid, user)
    await db.sales_orders.update_one({"id": oid}, {"$set": {"is_deleted": True, "deleted_at": now_iso(), "stock_deducted": False}})
    await audit(bid, user, "delete", "sales_orders", oid)
    return {"ok": True}


# ---------- E. Import marketplace ----------
ORDER_FIELDS = [
    ("order_id", "Order ID", True), ("date", "Tanggal", False), ("sku", "SKU", False), ("product_name", "Nama Produk", False), ("qty", "Qty", True),
    ("selling_price", "Harga Jual", True), ("normal_price", "Harga Normal", False), ("discount", "Diskon", False), ("voucher", "Voucher", False),
    ("shipping_fee", "Ongkir", False), ("shipping_subsidy", "Subsidi Ongkir", False), ("admin_fee", "Biaya Admin", False), ("service_fee", "Biaya Layanan", False),
    ("transaction_fee", "Biaya Transaksi", False), ("other_marketplace_fee", "Biaya Marketplace Lain", False), ("ad_fee", "Biaya Iklan", False), ("refund", "Refund", False),
    ("customer", "Customer", False), ("status", "Status", False), ("notes", "Keterangan", False),
]
ALIASES = {
    "order_id": ["order id", "no. pesanan", "nomor pesanan", "order sn", "order_sn", "order number", "no pesanan", "invoice", "nomor invoice"],
    "date": ["tanggal", "waktu pesanan dibuat", "order created time", "created time", "tanggal pembayaran", "date", "order date", "waktu pembayaran dilakukan"],
    "sku": ["sku", "sku induk", "nomor referensi sku", "seller sku", "sku id", "kode produk"],
    "product_name": ["nama produk", "product name", "produk", "nama variasi", "product"],
    "qty": ["jumlah", "qty", "quantity", "kuantitas", "jumlah produk dibeli"],
    "selling_price": ["harga setelah diskon", "harga jual", "sku unit original price", "sku subtotal after discount", "harga satuan", "price", "harga"],
    "normal_price": ["harga awal", "harga normal", "sku unit original price", "harga asli"],
    "discount": ["diskon", "total diskon", "discount", "diskon dari penjual", "seller discount"],
    "voucher": ["voucher", "voucher ditanggung penjual", "seller voucher", "platform discount"],
    "shipping_fee": ["ongkos kirim", "ongkir", "shipping fee", "ongkos kirim dibayar oleh pembeli", "biaya pengiriman"],
    "shipping_subsidy": ["subsidi ongkir", "shipping subsidy", "estimasi potongan biaya pengiriman", "diskon ongkir"],
    "admin_fee": ["biaya administrasi", "biaya admin", "admin fee", "platform fee", "commission fee", "komisi"],
    "service_fee": ["biaya layanan", "service fee", "biaya jasa"],
    "transaction_fee": ["biaya transaksi", "transaction fee", "payment fee", "biaya pembayaran"],
    "other_marketplace_fee": ["biaya lainnya", "other fee", "biaya marketplace lain"],
    "ad_fee": ["biaya iklan", "ads", "advertising fee", "iklan"],
    "refund": ["refund", "pengembalian dana", "total refund", "returned amount", "jumlah pengembalian"],
    "customer": ["username (pembeli)", "nama penerima", "pembeli", "customer", "buyer username", "recipient", "nama pembeli"],
    "status": ["status pesanan", "status", "order status"],
    "notes": ["catatan", "keterangan", "notes", "pesan dari pembeli"],
}
STATUS_MAP = {"pending": "Pending", "belum bayar": "Pending", "unpaid": "Pending", "to ship": "Diproses", "perlu dikirim": "Diproses", "diproses": "Diproses", "processing": "Diproses", "awaiting shipment": "Diproses",
              "dikirim": "Dikirim", "shipped": "Dikirim", "shipping": "Dikirim", "in transit": "Dikirim", "sedang dikirim": "Dikirim", "selesai": "Selesai", "completed": "Selesai", "delivered": "Selesai", "terkirim": "Selesai",
              "dibatalkan": "Dibatalkan", "cancelled": "Dibatalkan", "canceled": "Dibatalkan", "batal": "Dibatalkan", "dikembalikan": "Dikembalikan", "returned": "Dikembalikan", "retur": "Dikembalikan", "refund": "Refund", "refunded": "Refund", "pengembalian dana": "Refund"}


def read_table(data: bytes, filename: str):
    try:
        if filename.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(data), dtype=str)
        else:
            df = pd.read_csv(io.BytesIO(data), sep=None, engine="python", dtype=str)
    except Exception as e:
        raise HTTPException(400, f"File tidak dapat dibaca: {e}")
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")


def parse_number(v):
    s = str(v or "").strip().replace("Rp", "").replace("IDR", "").replace(" ", "")
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) <= 2 else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[-1]) == 3):
        s = s.replace(".", "")
    return float(s)


def parse_date(v):
    s = str(v or "").strip()
    if not s:
        return today_str()
    ts = pd.to_datetime(s, dayfirst=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError("format tanggal tidak dikenali")
    return ts.date().isoformat()


@router.post("/import/preview")
async def import_preview(channel: str = Form(...), file: UploadFile = File(...), user=Depends(current_user)):
    check_channel(channel)
    df = read_table(await file.read(), file.filename or "")
    if df.empty:
        raise HTTPException(400, "File kosong")
    cols = list(df.columns)
    lower = {c.lower().strip(): c for c in cols}
    mapping = {}
    for field, aliases in ALIASES.items():
        for a in aliases:
            if a in lower and lower[a] not in mapping.values():
                mapping[field] = lower[a]
                break
    rows = [{str(k): str(v) for k, v in r.items()} for r in df.to_dict("records")]
    return {"filename": file.filename, "channel": channel, "columns": cols, "suggested_mapping": mapping, "rows": rows, "row_count": len(rows),
            "fields": [{"key": k, "label": l, "required": r} for k, l, r in ORDER_FIELDS]}


class ImportValidateIn(BaseModel):
    channel: str
    mapping: dict
    rows: List[dict]
    default_status: str = "Selesai"


async def resolve_products(bid):
    prods = await db.products.find(Q(bid), {"_id": 0, "id": 1, "name": 1, "sku": 1}).to_list(10000)
    by_sku = {(p.get("sku") or "").strip().lower(): p for p in prods if p.get("sku")}
    by_name = {p["name"].strip().lower(): p for p in prods}
    return by_sku, by_name


@router.post("/import/validate")
async def import_validate(body: ImportValidateIn, user=Depends(current_user)):
    bid = user["business_id"]
    check_channel(body.channel)
    missing = [l for k, l, req in ORDER_FIELDS if req and not body.mapping.get(k)]
    if missing:
        raise HTTPException(400, f"Kolom wajib belum dipetakan: {', '.join(missing)}")
    if not body.mapping.get("sku") and not body.mapping.get("product_name"):
        raise HTTPException(400, "Petakan kolom SKU atau Nama Produk untuk mengenali produk")
    by_sku, by_name = await resolve_products(bid)
    out, seen = [], set()
    for i, raw in enumerate(body.rows):
        g = lambda f: str(raw.get(body.mapping.get(f) or "", "")).strip()
        errors, data = [], {}
        data["order_id"] = g("order_id")
        if not data["order_id"]:
            errors.append({"field": "order_id", "value": "", "reason": "Order ID kosong"})
        for f in ("qty", "selling_price", "normal_price", "discount", "voucher", "shipping_fee", "shipping_subsidy", "admin_fee", "service_fee", "transaction_fee", "other_marketplace_fee", "ad_fee", "refund"):
            v = g(f) if body.mapping.get(f) else ""
            try:
                data[f] = parse_number(v) if v else (None if f in ("normal_price", *FEE_FIELDS) else 0.0)
                if data[f] is not None and data[f] < 0:
                    errors.append({"field": f, "value": v, "reason": "tidak boleh negatif"})
            except ValueError:
                errors.append({"field": f, "value": v, "reason": "bukan angka"})
                data[f] = 0.0
        if not data.get("qty"):
            errors.append({"field": "qty", "value": g("qty"), "reason": "Qty harus lebih dari 0"})
        try:
            data["date"] = parse_date(g("date")) if body.mapping.get("date") else today_str()
        except ValueError as e:
            errors.append({"field": "date", "value": g("date"), "reason": str(e)})
            data["date"] = today_str()
        sku, pname = g("sku").lower(), g("product_name").lower()
        prod = by_sku.get(sku) or by_name.get(pname)
        if not prod:
            errors.append({"field": "sku", "value": g("sku") or g("product_name"), "reason": "Produk tidak ditemukan di master Produk (cocokkan SKU/nama)"})
        data.update({"product_id": prod["id"] if prod else None, "product_name": prod["name"] if prod else g("product_name"), "sku": (prod.get("sku") if prod else g("sku")) or ""})
        st = g("status").lower() if body.mapping.get("status") else ""
        data["status"] = STATUS_MAP.get(st, body.default_status if not st else None)
        if data["status"] is None:
            errors.append({"field": "status", "value": g("status"), "reason": "Status tidak dikenali"})
            data["status"] = body.default_status
        data["customer"], data["notes"] = g("customer"), g("notes")
        key = (data["order_id"], data["sku"].lower())
        dup_file = key in seen
        seen.add(key)
        dup_db = bool(data["order_id"] and await find_duplicate(bid, data["order_id"], data["sku"]))
        out.append({"row": i + 2, "data": data, "errors": errors, "duplicate": dup_db or dup_file, "duplicate_source": "database" if dup_db else ("file" if dup_file else None)})
    return {"rows": out, "valid_count": sum(1 for r in out if not r["errors"] and not r["duplicate"]), "error_count": sum(1 for r in out if r["errors"]), "duplicate_count": sum(1 for r in out if r["duplicate"])}


class ImportCommitIn(BaseModel):
    channel: str
    filename: Optional[str] = ""
    rows: List[dict]


@router.post("/import/commit")
async def import_commit(body: ImportCommitIn, user=Depends(current_user)):
    bid = user["business_id"]
    check_channel(body.channel)
    imported, skipped, errors, warnings = 0, 0, [], []
    for r in body.rows:
        d = r.get("data", r)
        if not d.get("product_id"):
            errors.append({"row": r.get("row"), "reason": "Produk tidak ditemukan"})
            continue
        if await find_duplicate(bid, d["order_id"], d.get("sku") or ""):
            skipped += 1
            continue
        try:
            payload = OrderIn(order_id=d["order_id"], date=d.get("date"), channel=body.channel, customer=d.get("customer") or "", product_id=d["product_id"], qty=d["qty"], normal_price=d.get("normal_price"),
                              selling_price=d["selling_price"], discount=d.get("discount") or 0, voucher=d.get("voucher") or 0, shipping_fee=d.get("shipping_fee") or 0, shipping_subsidy=d.get("shipping_subsidy") or 0,
                              admin_fee=d.get("admin_fee"), service_fee=d.get("service_fee"), transaction_fee=d.get("transaction_fee"), other_marketplace_fee=d.get("other_marketplace_fee"),
                              ad_fee=d.get("ad_fee") or 0, refund=d.get("refund") or 0, status=d.get("status") or "Selesai", notes=d.get("notes") or "", source=f"import:{body.channel}")
            doc = await build_order(bid, payload, user, new_id())
            doc = await sync_stock(bid, doc, user)
            await db.sales_orders.insert_one(dict(doc))
            imported += 1
            if doc.get("stock_warning"):
                warnings.append({"row": r.get("row"), "order_id": d["order_id"], "reason": doc["stock_warning"]})
        except HTTPException as e:
            errors.append({"row": r.get("row"), "order_id": d.get("order_id"), "reason": e.detail})
    log = {"id": new_id(), "business_id": bid, "channel": body.channel, "filename": body.filename or "", "rows_total": len(body.rows), "imported": imported, "skipped_duplicates": skipped, "errors": errors, "warnings": warnings, "created_by": user["id"], "created_at": now_iso()}
    await db.marketplace_imports.insert_one(dict(log))
    await audit(bid, user, "import", "sales_orders", log["id"], {"imported": imported, "skipped": skipped})
    return log


@router.get("/import/history")
async def import_history(user=Depends(current_user)):
    return await db.marketplace_imports.find({"business_id": user["business_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


# ---------- G. Settlement / Payout ----------
class SettlementIn(BaseModel):
    channel: str
    settlement_id: str
    settlement_date: Optional[str] = None
    order_id: str
    gross_sales: float = 0
    discount: float = 0
    voucher: float = 0
    marketplace_fee: float = 0
    shipping_fee: float = 0
    advertising_fee: float = 0
    refund: float = 0
    other_deduction: float = 0
    actual_payout: float = 0
    payment_account_id: Optional[str] = None
    notes: Optional[str] = ""


def settlement_calc(b: SettlementIn):
    for f in ("gross_sales", "discount", "voucher", "marketplace_fee", "shipping_fee", "advertising_fee", "refund", "other_deduction", "actual_payout"):
        num(getattr(b, f), f)
    expected = b.gross_sales - b.discount - b.voucher - b.marketplace_fee - b.shipping_fee - b.advertising_fee - b.refund - b.other_deduction
    diff = b.actual_payout - expected
    status = "Refunded" if b.refund > 0 and b.actual_payout <= 0 else "Pending" if b.actual_payout == 0 else "Matched" if abs(diff) < 1 else "Difference"
    return {"expected_payout": R(expected), "difference": R(diff), "status": status}


async def settlement_doc(bid, body: SettlementIn, sid, existing=None):
    check_channel(body.channel)
    if not body.settlement_id.strip() or not body.order_id.strip():
        raise HTTPException(400, "Settlement ID dan Order ID wajib diisi")
    acc_name = ""
    if body.payment_account_id:
        acc = await db.cash_accounts.find_one(Q(bid, id=body.payment_account_id), {"_id": 0})
        if not acc:
            raise HTTPException(400, "Akun kas tidak ditemukan")
        acc_name = acc["name"]
    orders = await db.sales_orders.find(Q(bid, order_id=body.order_id.strip()), {"_id": 0, "id": 1, "seller_received": 1}).to_list(100)
    return {"id": sid, "business_id": bid, **body.model_dump(), "settlement_id": body.settlement_id.strip(), "order_id": body.order_id.strip(), "settlement_date": body.settlement_date or today_str(),
            "payment_account_name": acc_name, **settlement_calc(body), "linked_order_ids": [o["id"] for o in orders], "order_expected": R(sum(o.get("seller_received", 0) for o in orders)),
            "created_at": existing["created_at"] if existing else now_iso(), "updated_at": now_iso()}


async def post_settlement_cash(bid, doc):
    await db.cash_transactions.delete_many({"business_id": bid, "ref_type": "settlement", "ref_id": doc["id"]})
    if doc["actual_payout"] > 0 and doc.get("payment_account_id"):
        await post_cash(bid, doc["payment_account_id"], "in", doc["actual_payout"], "settlement", "settlement", doc["id"], f"Payout {doc['channel']} {doc['settlement_id']} (Order {doc['order_id']})", doc["settlement_date"])


@router.get("/settlements")
async def list_settlements(user=Depends(current_user), start: str = "", end: str = "", channel: str = "", status: str = ""):
    q = Q(user["business_id"], settlement_date=date_range(start, end))
    if channel:
        q["channel"] = channel
    if status:
        q["status"] = status
    return await db.marketplace_settlements.find(q, {"_id": 0}).sort([("settlement_date", -1), ("created_at", -1)]).to_list(10000)


@router.post("/settlements")
async def create_settlement(body: SettlementIn, user=Depends(current_user)):
    bid = user["business_id"]
    doc = await settlement_doc(bid, body, new_id())
    await db.marketplace_settlements.insert_one(dict(doc))
    await post_settlement_cash(bid, doc)
    await audit(bid, user, "create", "marketplace_settlements", doc["id"], {"settlement_id": doc["settlement_id"], "actual_payout": doc["actual_payout"]})
    return doc


@router.put("/settlements/{sid}")
async def update_settlement(sid: str, body: SettlementIn, user=Depends(current_user)):
    bid = user["business_id"]
    old = await db.marketplace_settlements.find_one(Q(bid, id=sid), {"_id": 0})
    if not old:
        raise HTTPException(404, "Settlement tidak ditemukan")
    doc = await settlement_doc(bid, body, sid, old)
    await db.marketplace_settlements.replace_one({"id": sid}, dict(doc))
    await post_settlement_cash(bid, doc)
    return doc


@router.delete("/settlements/{sid}")
async def delete_settlement(sid: str, user=Depends(current_user)):
    bid = user["business_id"]
    if not await db.marketplace_settlements.find_one(Q(bid, id=sid)):
        raise HTTPException(404, "Settlement tidak ditemukan")
    await db.cash_transactions.delete_many({"business_id": bid, "ref_type": "settlement", "ref_id": sid})
    await db.marketplace_settlements.update_one({"id": sid}, {"$set": {"is_deleted": True, "deleted_at": now_iso()}})
    return {"ok": True}


# ---------- F. Rekonsiliasi ----------
@router.get("/reconciliation")
async def reconciliation(user=Depends(current_user), start: str = "", end: str = "", channel: str = "", status: str = ""):
    bid = user["business_id"]
    q = Q(bid, date=date_range(start, end), status={"$nin": ["Pending", "Dibatalkan"]})
    if channel:
        q["channel"] = channel
    orders = await db.sales_orders.find(q, {"_id": 0}).to_list(20000)
    setts = await db.marketplace_settlements.find(Q(bid, order_id={"$in": list({o["order_id"] for o in orders})}), {"_id": 0}).to_list(20000)
    by_order = defaultdict(list)
    for s in setts:
        by_order[(s["channel"], s["order_id"])].append(s)
    grouped = defaultdict(list)
    for o in orders:
        grouped[(o["channel"], o["order_id"])].append(o)
    rows = []
    for (ch, oid), os_ in grouped.items():
        ss = by_order.get((ch, oid), [])
        total_sales = sum(o["gross_revenue"] for o in os_)
        deductions = sum(o["discount"] + o["voucher"] + o["marketplace_fee_total"] + o["ad_fee"] + o["refund"] for o in os_)
        expected = sum(o["seller_received"] for o in os_)
        actual = sum(s["actual_payout"] for s in ss)
        diff = actual - expected
        if any(o["status"] in REFUND_STATUSES for o in os_):
            st = "Refunded"
        elif not ss or all(s["actual_payout"] == 0 for s in ss):
            st = "Pending"
        else:
            st = "Matched" if abs(diff) < 1 else "Difference"
        rows.append({"channel": ch, "order_id": oid, "date": min(o["date"] for o in os_), "order_count": len(os_), "products": ", ".join(o["product_name"] for o in os_), "total_sales": R(total_sales),
                     "total_deductions": R(deductions), "expected_payout": R(expected), "actual_payout": R(actual), "difference": R(diff), "status": st,
                     "settlement_ids": [s["settlement_id"] for s in ss], "order_status": os_[0]["status"] if len(os_) == 1 else "Campuran"})
    if status:
        rows = [r for r in rows if r["status"] == status]
    rows.sort(key=lambda r: r["date"], reverse=True)
    summary = {k: R(sum(r[k] for r in rows)) for k in ("total_sales", "total_deductions", "expected_payout", "actual_payout", "difference")}
    summary["counts"] = {s: sum(1 for r in rows if r["status"] == s) for s in ("Matched", "Difference", "Pending", "Refunded")}
    return {"summary": summary, "rows": rows}


# ---------- I/J. Dashboard & Laporan ----------
async def filtered_orders(bid, start, end, channel, product_id, sku, status):
    q = Q(bid, date=date_range(start, end))
    for k, v in (("channel", channel), ("product_id", product_id), ("sku", sku), ("status", status)):
        if v:
            q[k] = v
    return await db.sales_orders.find(q, {"_id": 0}).to_list(50000)


def summarize(orders):
    active = [o for o in orders if o["status"] not in ("Pending", "Dibatalkan")]
    s = {k: R(sum(o[k] for o in active)) for k in ("gross_revenue", "net_revenue", "hpp_total", "packaging_cost", "marketplace_fee_total", "ad_fee", "other_operational_fee", "refund", "gross_profit", "net_profit", "discount", "voucher")}
    s["order_count"] = len({o["order_id"] for o in active})
    s["line_count"] = len(active)
    s["qty_sold"] = R(sum(o["qty"] for o in active))
    s["aov"] = R(safe_div(s["net_revenue"], s["order_count"]))
    s["margin_pct"] = round(safe_div(s["net_profit"], s["net_revenue"]) * 100 if s["net_revenue"] > 0 else 0.0, 2)
    s["cancelled_count"] = sum(1 for o in orders if o["status"] == "Dibatalkan")
    s["pending_count"] = sum(1 for o in orders if o["status"] == "Pending")
    return s


def group_by(orders, key):
    agg = defaultdict(list)
    for o in orders:
        if o["status"] in ("Pending", "Dibatalkan"):
            continue
        agg[o[key] if isinstance(key, str) else key(o)].append(o)
    return [{"key": k, **summarize(v)} for k, v in sorted(agg.items())]


@router.get("/dashboard")
async def dashboard(user=Depends(current_user), start: str = "", end: str = "", channel: str = "", product_id: str = "", sku: str = "", status: str = ""):
    orders = await filtered_orders(user["business_id"], start, end, channel, product_id, sku, status)
    daily = group_by(orders, "date")
    return {"summary": summarize(orders), "daily": daily, "by_channel": group_by(orders, "channel"),
            "by_product": sorted(group_by(orders, lambda o: f"{o['product_name']}" + (f" ({o['sku']})" if o.get("sku") else "")), key=lambda r: -r["net_revenue"])[:15],
            "by_status": [{"status": s, "count": sum(1 for o in orders if o["status"] == s)} for s in STATUSES]}


REPORT_TYPES = ("sales", "hpp", "packaging", "marketplace-fee", "advertising", "settlement", "reconciliation", "profit", "products", "channels")


@router.get("/reports/{rtype}")
async def report(rtype: str, user=Depends(current_user), start: str = "", end: str = "", channel: str = "", product_id: str = "", sku: str = ""):
    bid = user["business_id"]
    if rtype not in REPORT_TYPES:
        raise HTTPException(404, "Jenis laporan tidak dikenal")
    if rtype == "settlement":
        rows = await list_settlements(user, start, end, channel, "")
        return {"summary": {k: R(sum(r[k] for r in rows)) for k in ("gross_sales", "expected_payout", "actual_payout", "difference")}, "rows": rows}
    if rtype == "reconciliation":
        return await reconciliation(user, start, end, channel, "")
    orders = await filtered_orders(bid, start, end, channel, product_id, sku, "")
    summary = summarize(orders)
    if rtype == "products":
        return {"summary": summary, "rows": sorted(group_by(orders, lambda o: f"{o['product_name']}|{o.get('sku') or ''}"), key=lambda r: -r["net_revenue"])}
    if rtype == "channels":
        return {"summary": summary, "rows": group_by(orders, "channel")}
    if rtype == "profit":
        return {"summary": summary, "rows": group_by(orders, "date")}
    rows = [o for o in sorted(orders, key=lambda o: (o["date"], o["created_at"]), reverse=True) if o["status"] not in ("Pending", "Dibatalkan") or rtype == "sales"]
    return {"summary": summary, "rows": rows}


@router.get("/meta")
async def marketplace_meta(user=Depends(current_user)):
    return {"channels": CHANNELS, "statuses": STATUSES, "stock_statuses": sorted(STOCK_STATUSES), "fee_categories": [{"value": k, "label": l} for k, l in (("admin", "Biaya Admin"), ("service", "Biaya Layanan"), ("transaction", "Biaya Transaksi"), ("other", "Biaya Marketplace Lainnya"))],
            "import_fields": [{"key": k, "label": l, "required": r} for k, l, r in ORDER_FIELDS]}
