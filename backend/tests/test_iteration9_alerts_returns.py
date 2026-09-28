"""Iteration 9 tests: low-stock alerts (banner/daily/cron) + return reasons."""
import os, uuid, pytest, requests

def _load_url():
    u = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if u:
        return u.rstrip("/")
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/")
    return ""
BASE_URL = _load_url()
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@keuangan.com"
ADMIN_PASS = "Admin12345!"
# Load webhook secret directly from backend/.env
def _load_secret():
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith("WEBHOOK_CRON_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""
WEBHOOK_SECRET = _load_secret()


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Alerts ----------------
def test_stock_alerts_shape(H):
    r = requests.get(f"{API}/alerts/stock", headers=H, timeout=30)
    assert r.status_code == 200
    j = r.json()
    for k in ("count", "critical", "material_count", "product_count", "alerts"):
        assert k in j
    assert j["count"] == len(j["alerts"])


def test_stock_alerts_daily(H):
    r1 = requests.get(f"{API}/alerts/stock/daily", headers=H, timeout=30)
    assert r1.status_code == 200
    j1 = r1.json()
    assert "today" in j1 and "history" in j1
    assert j1["today"]["count"] >= 0
    hist_len = len(j1["history"])
    assert hist_len >= 1
    assert "new_items" in j1 and "resolved_items" in j1
    # Alert count matches
    r_alerts = requests.get(f"{API}/alerts/stock", headers=H).json()
    assert j1["today"]["count"] == r_alerts["count"]
    # Call again same day - history length unchanged (upsert)
    r2 = requests.get(f"{API}/alerts/stock/daily", headers=H, timeout=30)
    assert r2.status_code == 200
    assert len(r2.json()["history"]) == hist_len


def test_create_critical_and_low_alerts(H):
    suffix = uuid.uuid4().hex[:6]
    # product with min_stock 5, stock 0 (default) → critical
    p = requests.post(f"{API}/products", headers=H, json={
        "name": f"TEST_IT9_Prod_{suffix}", "sku": f"TEST-IT9-{suffix}",
        "unit": "pcs", "selling_price": 10000, "min_stock": 5
    }, timeout=30)
    assert p.status_code in (200, 201), p.text
    pid = p.json()["id"]
    # material with initial_stock below min_stock → low
    m = requests.post(f"{API}/materials", headers=H, json={
        "name": f"TEST_IT9_Mat_{suffix}", "purchase_unit": "kg", "usage_unit": "gram",
        "conversion_factor": 1000, "last_price": 10000, "min_stock": 500, "initial_stock": 100
    }, timeout=30)
    assert m.status_code in (200, 201), m.text
    mid = m.json()["id"]
    alerts = requests.get(f"{API}/alerts/stock", headers=H).json()["alerts"]
    p_alert = next((a for a in alerts if a["item_id"] == pid), None)
    m_alert = next((a for a in alerts if a["item_id"] == mid), None)
    assert p_alert is not None and p_alert["severity"] == "critical"
    assert m_alert is not None and m_alert["severity"] == "low"


# ---------------- Cron ----------------
def test_cron_no_auth():
    r = requests.post(f"{API}/cron/stock-daily", timeout=30)
    assert r.status_code == 401


def test_cron_wrong_token():
    r = requests.post(f"{API}/cron/stock-daily", headers={"Authorization": "Bearer wrong"}, timeout=30)
    assert r.status_code == 401


def test_cron_correct_and_idempotent():
    run_id = f"test-run-{uuid.uuid4().hex[:8]}"
    h = {"Authorization": f"Bearer {WEBHOOK_SECRET}", "X-Webhook-Id": run_id}
    r = requests.post(f"{API}/cron/stock-daily", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") is True
    # duplicate
    r2 = requests.post(f"{API}/cron/stock-daily", headers=h, timeout=30)
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True


# ---------------- Return reasons ----------------
@pytest.fixture(scope="module")
def any_product(H):
    prods = requests.get(f"{API}/products", headers=H).json()
    assert prods
    return prods[0]


def _make_order(H, pid, **kwargs):
    body = {"order_id": f"TEST_IT9_{uuid.uuid4().hex[:8]}", "channel": "Shopee",
            "product_id": pid, "qty": 2, "selling_price": 20000, "status": "Selesai"}
    body.update(kwargs)
    r = requests.post(f"{API}/marketplace/orders", headers=H, json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_refund_reason_explicit(H, any_product):
    o = _make_order(H, any_product["id"], refund_qty=1, refund_reason="Rusak")
    assert o["refund_reason"] == "Rusak"


def test_refund_reason_freetext_normalized(H, any_product):
    o = _make_order(H, any_product["id"], status="Dikembalikan",
                    refund_reason="barang salah kirim", refund_qty=2, refund=40000)
    assert o["refund_reason"] == "Salah kirim"


def test_refund_reason_default_lainnya(H, any_product):
    o = _make_order(H, any_product["id"], status="Refund", refund_qty=2, refund=40000)
    assert o["refund_reason"] == "Lainnya"


def test_no_reason_for_normal_order(H, any_product):
    o = _make_order(H, any_product["id"], status="Selesai")
    assert o["refund_reason"] == ""


def test_returns_report(H):
    r = requests.get(f"{API}/marketplace/reports/returns", headers=H, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "summary" in j and "rows" in j and "detail" in j
    s = j["summary"]
    for k in ("return_orders", "total_orders", "return_rate_pct", "refund_amount", "refund_qty", "hpp_lost", "top_reason"):
        assert k in s
    # detail contains only return orders (no plain Selesai without refund)
    for d in j["detail"]:
        assert d["status"] in ("Dikembalikan", "Refund") or (d.get("refund_qty") or 0) > 0 or (d.get("refund") or 0) > 0
    # per-reason rows have proper structure
    for row in j["rows"]:
        assert row["order_count"] >= 1
        assert "refund_amount" in row


def test_marketplace_meta_refund_reasons(H):
    r = requests.get(f"{API}/marketplace/meta", headers=H, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "refund_reasons" in j
    assert "Rusak" in j["refund_reasons"] and "Lainnya" in j["refund_reasons"]


# ---------------- Import ----------------
def test_import_validate_and_commit_with_reason(H, any_product):
    order_id = f"TEST_IT9_IMP_{uuid.uuid4().hex[:8]}"
    body = {
        "channel": "Shopee",
        "mapping": {"order_id": "Order ID", "qty": "Qty", "selling_price": "Harga", "sku": "SKU",
                    "refund_qty": "Qty Retur", "refund_reason": "Alasan", "status": "Status"},
        "rows": [{"Order ID": order_id, "Qty": "1", "Harga": "15000", "SKU": any_product.get("sku") or "",
                  "Qty Retur": "1", "Alasan": "barang rusak parah", "Status": "dikembalikan"}],
        "default_status": "Selesai"
    }
    v = requests.post(f"{API}/marketplace/import/validate", headers=H, json=body, timeout=30)
    assert v.status_code == 200, v.text
    jv = v.json()
    assert jv["rows"][0]["data"]["refund_reason"] == "Rusak"
    # commit
    c = requests.post(f"{API}/marketplace/import/commit", headers=H, json={
        "channel": "Shopee", "filename": "test.csv", "rows": jv["rows"]
    }, timeout=30)
    assert c.status_code == 200, c.text
    assert c.json()["imported"] >= 1
    # verify stored order has refund_reason
    orders = requests.get(f"{API}/marketplace/orders", headers=H, params={"q": order_id}).json()
    assert orders and orders[0]["refund_reason"] == "Rusak"


# ---------------- Regression ----------------
def test_regression_reports_and_dashboard(H):
    for rt in ("sales", "products", "channels"):
        r = requests.get(f"{API}/marketplace/reports/{rt}", headers=H, timeout=30)
        assert r.status_code == 200, f"{rt}: {r.text}"
    r = requests.get(f"{API}/dashboard", headers=H, timeout=30)
    assert r.status_code == 200
