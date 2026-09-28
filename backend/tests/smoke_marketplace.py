import os, sys, io, json, requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"] + "/api"
S = requests.Session()
r = S.post(f"{BASE}/auth/login", json={"email": "owner@keuangan-v1.app", "password": "3kpgWW63mV8onkZN"})
S.headers["Authorization"] = f"Bearer {r.json()['token']}"


def call(m, p, ok=200, **kw):
    r = S.request(m, f"{BASE}{p}", **kw)
    assert r.status_code == ok, f"{m} {p} -> {r.status_code} {r.text[:300]}"
    return r.json() if r.text else None


def approx(a, b, m=""):
    assert abs(a - b) < 0.01, f"{m}: {a} != {b}"


# cleanup previous run
for o in call("GET", "/marketplace/orders?q=SMOKE"):
    call("DELETE", f"/marketplace/orders/{o['id']}")
for s in call("GET", "/marketplace/settlements"):
    if s["settlement_id"].startswith("SMOKE"):
        call("DELETE", f"/marketplace/settlements/{s['id']}")
for f in call("GET", "/marketplace/fees"):
    if f["name"].startswith("SMOKE"):
        call("DELETE", f"/marketplace/fees/{f['id']}")

# fees: Shopee admin 5% + service nominal 1250 (expired one ignored)
fee1 = call("POST", "/marketplace/fees", json={"name": "SMOKE Admin Fee", "channel": "Shopee", "category": "admin", "fee_type": "percent", "value": 5})
fee2 = call("POST", "/marketplace/fees", json={"name": "SMOKE Service Fee", "channel": "Shopee", "category": "service", "fee_type": "nominal", "value": 1250})
fee3 = call("POST", "/marketplace/fees", json={"name": "SMOKE Old Fee", "channel": "Shopee", "category": "transaction", "fee_type": "percent", "value": 50, "valid_to": "2020-01-01"})
call("POST", "/marketplace/fees", ok=400, json={"name": "x", "channel": "Lazada", "value": 1})
pv = call("GET", "/marketplace/fees/preview?channel=Shopee&date=2026-06-15&base=100000")
approx(pv["total"], 6250, "fee preview")

# packaging items + config
it1 = call("POST", "/marketplace/packaging/items", json={"name": "SMOKE Solasi", "purchase_price": 6600, "purchase_qty": 6600, "unit": "cm"})
it2 = call("POST", "/marketplace/packaging/items", json={"name": "SMOKE Bubble Wrap", "purchase_price": 50000, "purchase_qty": 5000, "unit": "cm"})
approx(it1["unit_price"], 1.0, "unit price")
cfg = call("POST", "/marketplace/packaging/configs", json={"name": "SMOKE Solasi + Bubble Wrap", "components": [{"item_id": it1["id"], "qty": 100}, {"item_id": it2["id"], "qty": 140}]})
approx(cfg["cost_per_product"], 100 + 1400, "config cost")  # 100cm*1 + 140cm*10 = 1500
call("DELETE", f"/marketplace/packaging/items/{it1['id']}", ok=400)  # in use

# product with stock 10 & HPP via adjust
prod = call("POST", "/products", json={"name": "SMOKE Produk MP", "sku": "SMOKE-SKU-1", "unit": "pcs", "selling_price": 20000})
call("PUT", f"/products/{prod['id']}", json={"name": "SMOKE Produk MP", "sku": "SMOKE-SKU-1", "unit": "pcs", "selling_price": 20000})
# set avg_hpp directly not possible via API without production -> use inventory adjust (cost = avg_hpp = 0). Use manual hpp check = 0 then.
call("POST", "/inventory/adjust", json={"item_type": "product", "item_id": prod["id"], "qty": 10, "direction": "in"})
call("PUT", "/marketplace/packaging/assign", json={"product_id": prod["id"], "packaging_cost_id": cfg["id"]})

# order: qty 5, price 20000, discount 5000, voucher 2000, ad 3000 -> gross 100000, net 93000, packaging 7500, fees 5%*93000=4650 + 1250
o = call("POST", "/marketplace/orders", json={"order_id": "SMOKE-001", "date": "2026-06-15", "channel": "Shopee", "product_id": prod["id"], "qty": 5, "selling_price": 20000, "discount": 5000, "voucher": 2000, "ad_fee": 3000, "status": "Selesai", "customer": "Budi"})
approx(o["gross_revenue"], 100000, "gross"); approx(o["net_revenue"], 93000, "net"); approx(o["packaging_cost"], 7500, "packaging")
approx(o["admin_fee"], 4650, "admin"); approx(o["service_fee"], 1250, "service"); approx(o["transaction_fee"], 0, "expired fee ignored")
approx(o["gross_profit"], 93000 - o["hpp_total"] - 7500, "gp"); approx(o["net_profit"], o["gross_profit"] - 5900 - 3000, "np")
approx(o["margin_pct"], round(o["net_profit"] / 93000 * 100, 2), "margin"); assert o["stock_deducted"] is True
approx(call("GET", f"/products/{prod['id']}")["stock"], 5, "stock after order")
# duplicate
call("POST", "/marketplace/orders", ok=400, json={"order_id": "SMOKE-001", "channel": "Shopee", "product_id": prod["id"], "qty": 1, "selling_price": 1})
# status -> Dibatalkan returns stock, -> Selesai deducts once again
o2 = call("PATCH", f"/marketplace/orders/{o['id']}/status", json={"status": "Dibatalkan"})
assert o2["stock_deducted"] is False; approx(call("GET", f"/products/{prod['id']}")["stock"], 10, "stock restored")
o3 = call("PATCH", f"/marketplace/orders/{o['id']}/status", json={"status": "Dikirim"})
o3 = call("PATCH", f"/marketplace/orders/{o['id']}/status", json={"status": "Selesai"})
approx(call("GET", f"/products/{prod['id']}")["stock"], 5, "no double deduction"); approx(o3["admin_fee"], 4650, "fees kept after status")
# refund status -> auto refund amount, margin 0, no NaN
o4 = call("PATCH", f"/marketplace/orders/{o['id']}/status", json={"status": "Refund"})
approx(o4["refund"], 93000, "auto refund"); approx(o4["net_revenue"], 0, "net 0"); assert o4["margin_pct"] == 0; assert o4["stock_deducted"] is False
call("PATCH", f"/marketplace/orders/{o['id']}/status", json={"status": "Selesai"})
o5 = call("PUT", f"/marketplace/orders/{o['id']}", json={"order_id": "SMOKE-001", "date": "2026-06-15", "channel": "Shopee", "product_id": prod["id"], "qty": 5, "selling_price": 20000, "discount": 5000, "voucher": 2000, "ad_fee": 3000, "refund": 0, "status": "Selesai"})
approx(o5["net_revenue"], 93000, "net after reset refund")
# pending order: no stock deduction & excluded from dashboard
op = call("POST", "/marketplace/orders", json={"order_id": "SMOKE-002", "date": "2026-06-16", "channel": "Website", "product_id": prod["id"], "qty": 2, "selling_price": 20000, "status": "Pending"})
assert op["stock_deducted"] is False and op["marketplace_fee_total"] == 0
# insufficient stock -> warning not crash
ow = call("POST", "/marketplace/orders", json={"order_id": "SMOKE-003", "date": "2026-06-16", "channel": "Tokopedia", "product_id": prod["id"], "qty": 50, "selling_price": 20000, "status": "Selesai"})
assert ow["stock_warning"] and ow["stock_deducted"] is False

# import CSV (Shopee-like headers), includes dup SMOKE-001 and unknown product
csv = "No. Pesanan,Waktu Pesanan Dibuat,Nomor Referensi SKU,Nama Produk,Jumlah,Harga Setelah Diskon,Voucher Ditanggung Penjual,Status Pesanan,Username (Pembeli)\n" \
      "SMOKE-IMP-1,15/06/2026 10:00,SMOKE-SKU-1,SMOKE Produk MP,2,\"Rp 20.000\",\"1.000\",Selesai,andi\n" \
      "SMOKE-001,15/06/2026,SMOKE-SKU-1,SMOKE Produk MP,5,20000,0,Selesai,budi\n" \
      "SMOKE-IMP-2,2026-06-17,UNKNOWN-SKU,Produk Tidak Ada,1,10000,0,Dikirim,cici\n" \
      "SMOKE-IMP-3,17/06/2026,SMOKE-SKU-1,SMOKE Produk MP,abc,10000,0,Dibatalkan,dedi\n"
pv = call("POST", "/marketplace/import/preview", data={"channel": "Shopee"}, files={"file": ("shopee.csv", csv.encode(), "text/csv")})
m = pv["suggested_mapping"]
assert m["order_id"] == "No. Pesanan" and m["sku"] == "Nomor Referensi SKU" and m["qty"] == "Jumlah" and m["status"] == "Status Pesanan", m
va = call("POST", "/marketplace/import/validate", json={"channel": "Shopee", "mapping": m, "rows": pv["rows"]})
assert va["valid_count"] == 1 and va["duplicate_count"] == 1 and va["error_count"] == 2, va
assert va["rows"][0]["data"]["selling_price"] == 20000 and va["rows"][0]["data"]["voucher"] == 1000 and va["rows"][0]["data"]["date"] == "2026-06-15"
assert any(e["field"] == "qty" for e in va["rows"][3]["errors"])
ok_rows = [r for r in va["rows"] if not r["errors"] and not r["duplicate"]]
res = call("POST", "/marketplace/import/commit", json={"channel": "Shopee", "filename": "shopee.csv", "rows": ok_rows})
assert res["imported"] == 1 and res["skipped_duplicates"] == 0
res2 = call("POST", "/marketplace/import/commit", json={"channel": "Shopee", "filename": "shopee.csv", "rows": ok_rows})
assert res2["imported"] == 0 and res2["skipped_duplicates"] == 1, "re-import must skip duplicates"
approx(call("GET", f"/products/{prod['id']}")["stock"], 3, "import deducted stock once (5-2)")
# excel import
import pandas as pd
buf = io.BytesIO(); pd.DataFrame([{"Order ID": "SMOKE-XL-1", "SKU": "SMOKE-SKU-1", "Qty": 1, "Harga Jual": 15000, "Status": "Selesai"}]).to_excel(buf, index=False)
pvx = call("POST", "/marketplace/import/preview", data={"channel": "TikTok Shop"}, files={"file": ("tiktok.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
vax = call("POST", "/marketplace/import/validate", json={"channel": "TikTok Shop", "mapping": pvx["suggested_mapping"], "rows": pvx["rows"]})
assert vax["valid_count"] == 1, vax
call("POST", "/marketplace/import/commit", json={"channel": "TikTok Shop", "rows": vax["rows"]})

# settlement + reconciliation
acc = call("GET", "/cash/accounts")[0]
st = call("POST", "/marketplace/settlements", json={"channel": "Shopee", "settlement_id": "SMOKE-STL-1", "settlement_date": "2026-06-20", "order_id": "SMOKE-001", "gross_sales": 100000, "discount": 5000, "voucher": 2000, "marketplace_fee": 5900, "advertising_fee": 3000, "actual_payout": 84100, "payment_account_id": acc["id"]})
approx(st["expected_payout"], 84100, "expected"); assert st["status"] == "Matched"
cash = [c for c in call("GET", "/cash/transactions") if c.get("ref_id") == st["id"]]
assert len(cash) == 1 and cash[0]["amount"] == 84100, "cash posted once"
rec = call("GET", "/marketplace/reconciliation?start=2026-06-01&end=2026-06-30")
row = next(r for r in rec["rows"] if r["order_id"] == "SMOKE-001")
approx(row["expected_payout"], o5["seller_received"], "recon expected"); assert row["status"] == "Matched", row
rowp = next(r for r in rec["rows"] if r["order_id"] == "SMOKE-IMP-1"); assert rowp["status"] == "Pending"

# dashboard & reports
d = call("GET", "/marketplace/dashboard?start=2026-06-01&end=2026-06-30&channel=Shopee")
s = d["summary"]; assert s["order_count"] == 2 and s["pending_count"] == 0, s
assert all(v == v and abs(v) != float("inf") for v in s.values() if isinstance(v, float))
for t in ("sales", "hpp", "packaging", "marketplace-fee", "advertising", "settlement", "reconciliation", "profit", "products", "channels"):
    rr = call("GET", f"/marketplace/reports/{t}?start=2026-06-01&end=2026-06-30"); assert "rows" in rr
call("GET", "/marketplace/reports/unknown", ok=404)
# legacy sales still work
assert isinstance(call("GET", "/sales"), list)
print("ALL MARKETPLACE SMOKE CHECKS PASSED")
