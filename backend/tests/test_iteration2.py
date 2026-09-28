"""Iteration 2 backend tests: PUT purchase/sale, stock alerts, material cost trend."""
import os
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE}/api"
ADMIN_EMAIL = "danarhuda59@gmail.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


def _find_material(admin, name_contains):
    r = admin.get(f"{API}/materials")
    assert r.status_code == 200
    for m in r.json():
        if name_contains.lower() in m["name"].lower():
            return m
    return None


def _find_product(admin, name_contains):
    r = admin.get(f"{API}/products")
    assert r.status_code == 200
    for p in r.json():
        if name_contains.lower() in p["name"].lower():
            return p
    return None


def _cash_balance(admin):
    r = admin.get(f"{API}/cash/accounts")
    assert r.status_code == 200
    return sum(float(a.get("balance") or 0) for a in r.json())


# ---------------- PUT /api/purchases/{id} ----------------
class TestUpdatePurchase:
    def test_update_purchase_reverses_and_reapplies(self, admin):
        mat = _find_material(admin, "Tepung Terigu")
        assert mat, "Demo material Tepung Terigu not found"
        mid = mat["id"]
        orig_stock = float(mat.get("stock") or 0)
        orig_last_price = float(mat.get("last_price") or 0)
        cash_before = _cash_balance(admin)

        # CREATE purchase 5 kg @ 13000
        create = admin.post(f"{API}/purchases", json={
            "items": [{"material_id": mid, "qty": 5, "unit": "kg", "price": 13000, "discount": 0}],
            "payment_method": "Tunai", "payment_status": "paid",
        })
        assert create.status_code == 200, create.text
        pdoc = create.json()
        pid = pdoc["id"]
        number = pdoc["number"]
        assert pdoc["total"] == 65000

        # verify stock increased by 5000 gram (kg->gram assumed)
        mat_after_create = _find_material(admin, "Tepung Terigu")
        assert abs(float(mat_after_create["stock"]) - (orig_stock + 5000)) < 1e-6, \
            f"expected +5000 got {mat_after_create['stock'] - orig_stock}"

        try:
            # PUT with qty 2 @ 14000
            upd = admin.put(f"{API}/purchases/{pid}", json={
                "items": [{"material_id": mid, "qty": 2, "unit": "kg", "price": 14000, "discount": 0}],
                "payment_method": "Tunai", "payment_status": "paid",
            })
            assert upd.status_code == 200, upd.text
            updoc = upd.json()
            assert updoc["number"] == number, "number should be preserved"
            assert updoc["total"] == 28000, f"total should be 28000, got {updoc['total']}"

            # Stock should be original + 2000 gram (not +7000)
            mat_after_upd = _find_material(admin, "Tepung Terigu")
            diff = float(mat_after_upd["stock"]) - orig_stock
            assert abs(diff - 2000) < 1e-6, f"stock should be original+2000, got diff={diff}"
            assert float(mat_after_upd["last_price"]) == 14000, f"last_price should be 14000, got {mat_after_upd['last_price']}"

            # price_history: only ONE entry with this purchase_id
            hist = admin.get(f"{API}/materials/{mid}/price-history")
            if hist.status_code == 200:
                entries = [h for h in hist.json() if h.get("purchase_id") == pid]
                assert len(entries) == 1, f"expected 1 price_history entry, got {len(entries)}"

            # cash balance: only -28000 vs before create
            cash_after = _cash_balance(admin)
            assert abs((cash_after - cash_before) - (-28000)) < 1.0, \
                f"cash delta expected -28000, got {cash_after - cash_before}"
        finally:
            # cleanup
            d = admin.delete(f"{API}/purchases/{pid}")
            assert d.status_code == 200
            mat_after_del = _find_material(admin, "Tepung Terigu")
            assert abs(float(mat_after_del["stock"]) - orig_stock) < 1e-6, "stock not restored after delete"

    def test_update_nonexistent_purchase_returns_404(self, admin):
        r = admin.put(f"{API}/purchases/nonexistent-{uuid.uuid4().hex}", json={
            "items": [{"material_id": "x", "qty": 1, "price": 1}],
        })
        assert r.status_code == 404


# ---------------- PUT /api/sales/{id} ----------------
class TestUpdateSale:
    def test_update_sale_reverses_and_reapplies(self, admin):
        # Find a product with enough stock (>= 5)
        r = admin.get(f"{API}/products")
        assert r.status_code == 200
        prod = None
        for p in r.json():
            if float(p.get("stock") or 0) >= 10 and float(p.get("avg_hpp") or 0) > 0:
                prod = p
                break
        if not prod:
            pytest.skip("No product with stock>=10 and avg_hpp>0 available")
        pid_prod = prod["id"]
        orig_stock = float(prod["stock"])
        avg_hpp = float(prod["avg_hpp"])
        price = float(prod.get("selling_price") or 20000) or 20000
        cash_before = _cash_balance(admin)

        # CREATE sale qty 3
        c = admin.post(f"{API}/sales", json={
            "channel": "Offline",
            "items": [{"product_id": pid_prod, "qty": 3, "price": price, "discount": 0}],
            "payment_method": "Tunai",
        })
        assert c.status_code == 200, c.text
        sdoc = c.json()
        sid = sdoc["id"]
        number = sdoc["number"]

        try:
            # PUT to qty 5, channel Shopee, platform_fee 2000
            upd = admin.put(f"{API}/sales/{sid}", json={
                "channel": "Shopee",
                "items": [{"product_id": pid_prod, "qty": 5, "price": price, "discount": 0}],
                "platform_fee": 2000,
                "payment_method": "Transfer Bank",
            })
            assert upd.status_code == 200, upd.text
            u = upd.json()
            assert u["number"] == number
            assert u["channel"] == "Shopee"
            assert abs(u["net_total"] - (5 * price - 2000)) < 0.01, f"net_total {u['net_total']}"
            assert abs(u["total_hpp"] - (5 * avg_hpp)) < 0.5, f"total_hpp {u['total_hpp']} vs {5*avg_hpp}"

            # product stock = original - 5
            p2 = admin.get(f"{API}/products").json()
            new_stock = next(x["stock"] for x in p2 if x["id"] == pid_prod)
            assert abs(new_stock - (orig_stock - 5)) < 1e-6, f"expected {orig_stock-5}, got {new_stock}"

            # cash delta = net_total (only, old sale cash reversed)
            cash_after = _cash_balance(admin)
            assert abs((cash_after - cash_before) - u["net_total"]) < 1.0, \
                f"cash delta expected {u['net_total']}, got {cash_after - cash_before}"
        finally:
            admin.delete(f"{API}/sales/{sid}")
            p3 = admin.get(f"{API}/products").json()
            restored = next(x["stock"] for x in p3 if x["id"] == pid_prod)
            assert abs(restored - orig_stock) < 1e-6, "sale delete did not restore stock"

    def test_update_nonexistent_sale_404(self, admin):
        r = admin.put(f"{API}/sales/nope-{uuid.uuid4().hex}", json={
            "items": [{"product_id": "x", "qty": 1, "price": 1}],
        })
        assert r.status_code == 404

    def test_update_sale_exceeding_stock_returns_400(self, admin):
        prod = None
        for p in admin.get(f"{API}/products").json():
            if float(p.get("stock") or 0) >= 1 and float(p.get("avg_hpp") or 0) > 0:
                prod = p
                break
        if not prod:
            pytest.skip("no suitable product")
        pid_prod = prod["id"]
        stock = float(prod["stock"])
        # create small sale
        c = admin.post(f"{API}/sales", json={
            "items": [{"product_id": pid_prod, "qty": 1, "price": 10000, "discount": 0}],
        })
        assert c.status_code == 200, c.text
        sid = c.json()["id"]
        try:
            # attempt qty larger than stock (after reversal)
            over = stock + 100
            r = admin.put(f"{API}/sales/{sid}", json={
                "items": [{"product_id": pid_prod, "qty": over, "price": 10000, "discount": 0}],
            })
            assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
        finally:
            admin.delete(f"{API}/sales/{sid}")


# ---------------- Stock alerts ----------------
class TestStockAlerts:
    def test_alerts_shape_and_demo_expectations(self, admin):
        r = admin.get(f"{API}/alerts/stock")
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("date", "count", "critical", "alerts"):
            assert k in data
        assert isinstance(data["alerts"], list)
        for a in data["alerts"]:
            assert a["suggested_qty"] >= 0
            assert a["estimated_cost"] >= 0
            # validate suggested formula: max(min + daily*14, min*2) - stock
            expected = max(a["min_stock"] + a["avg_daily_usage"] * 14, a["min_stock"] * 2) - a["stock"]
            expected = max(expected, 0)
            assert abs(a["suggested_qty"] - round(expected, 2)) < 0.05, \
                f"suggested_qty formula mismatch for {a['name']}: got {a['suggested_qty']} expected ~{expected}"
        # Look for demo-specific alerts (best-effort, non-fatal warnings)
        names = [a["name"] for a in data["alerts"]]
        print(f"Stock alerts ({data['count']}): {names}")


# ---------------- Material cost trend ----------------
class TestMaterialCostTrend:
    def test_trend_shape(self, admin):
        r = admin.get(f"{API}/dashboard/material-cost-trend")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("materials", "up_count", "down_count", "purchase_spend_current"):
            assert k in d
        assert isinstance(d["materials"], list)
        for m in d["materials"]:
            assert "prev_price" in m and "current_price" in m and "change_pct" in m
        # demo expectation - best effort
        by_name = {m["name"]: m for m in d["materials"]}
        print(f"Trend up={d['up_count']} down={d['down_count']} spend_cur={d['purchase_spend_current']}")
        if "Tapioka" in by_name:
            t = by_name["Tapioka"]
            print(f"Tapioka: {t['prev_price']} -> {t['current_price']} ({t['change_pct']}%)")
        if "Minyak Goreng" in by_name:
            mg = by_name["Minyak Goreng"]
            print(f"Minyak Goreng: {mg['prev_price']} -> {mg['current_price']} ({mg['change_pct']}%)")
