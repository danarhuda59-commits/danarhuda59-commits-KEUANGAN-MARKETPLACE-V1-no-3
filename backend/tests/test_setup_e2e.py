"""End-to-end smoke tests for Keuangan-1 setup verification.

Covers: /api/, auth login+me+register, add material, add product,
create recipe with 2 items (gram+kg) & compute HPP, HPP calculator,
purchase -> production -> sale flow, reports, demo seed, data isolation.

Run: pytest /app/backend/tests/test_setup_e2e.py -v -n0
"""
import os, uuid, time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # Fall back to reading frontend .env at runtime
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@keuangan.id", "password": "admin12345"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["email"] == ADMIN["email"]
    return data["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# -------- Basic API --------
def test_root():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert "message" in r.json()


def test_login_me_flow(admin_token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == ADMIN["email"]
    assert body["business"] and body["business"]["id"]


def test_me_without_token():
    r = requests.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 401


# -------- Materials --------
@pytest.fixture(scope="module")
def tapioka(admin_headers):
    payload = {
        "name": f"TEST_Tapioka_{uuid.uuid4().hex[:6]}",
        "purchase_unit": "kg", "usage_unit": "gram",
        "conversion_factor": 1000, "last_price": 10000, "min_stock": 0,
    }
    r = requests.post(f"{API}/materials", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["name"] == payload["name"]
    assert m["conversion_factor"] == 1000
    assert m["last_price"] == 10000
    assert m["price_per_usage"] == 10.0  # 10000 / 1000
    # GET verify persistence
    g = requests.get(f"{API}/materials/{m['id']}", headers=admin_headers, timeout=15)
    assert g.status_code == 200
    assert g.json()["id"] == m["id"]
    return m


@pytest.fixture(scope="module")
def gula(admin_headers):
    payload = {
        "name": f"TEST_Gula_{uuid.uuid4().hex[:6]}",
        "purchase_unit": "kg", "usage_unit": "gram",
        "conversion_factor": 1000, "last_price": 15000, "min_stock": 0,
    }
    r = requests.post(f"{API}/materials", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# -------- Products --------
@pytest.fixture(scope="module")
def baso_aci(admin_headers):
    payload = {"name": f"TEST_BasoAci_{uuid.uuid4().hex[:6]}", "unit": "cup", "selling_price": 12000}
    r = requests.post(f"{API}/products", json=payload, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["selling_price"] == 12000
    return p


# -------- Recipe & HPP math --------
@pytest.fixture(scope="module")
def recipe(admin_headers, tapioka, gula, baso_aci):
    body = {
        "product_id": baso_aci["id"],
        "name": f"TEST_Resep_BasoAci_{uuid.uuid4().hex[:6]}",
        "yield_qty": 20, "yield_unit": "cup",
        "selling_price": 12000,
        "items": [
            {"material_id": tapioka["id"], "qty": 500, "unit": "gram", "waste_pct": 0},
            {"material_id": gula["id"], "qty": 100, "unit": "gram", "waste_pct": 10},
        ],
        "extra_costs": [],
    }
    r = requests.post(f"{API}/recipes", json=body, headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    rec = r.json()
    cost = rec["cost"]
    assert cost["hpp_per_unit"] is not None and cost["hpp_per_unit"] > 0
    # Expected math:
    # tapioka cost = 500g * (10000/1000) * (1+0) = 5000
    # gula cost = 100g * (15000/1000) * 1.10 = 1650
    # material_total = 6650, yield 20 -> hpp_per_unit = 332.5
    assert abs(cost["material_total"] - 6650.0) < 0.5
    assert abs(cost["hpp_per_unit"] - 332.5) < 0.5
    return rec


def test_hpp_calculator_endpoint(admin_headers, tapioka, gula):
    body = {
        "items": [
            {"material_id": tapioka["id"], "qty": 500, "unit": "gram", "waste_pct": 0},
            {"material_id": gula["id"], "qty": 100, "unit": "gram", "waste_pct": 10},
        ],
        "extra_costs": [],
        "yield_qty": 20,
        "selling_price": 12000,
    }
    r = requests.post(f"{API}/hpp/calculate", json=body, headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    res = r.json()
    assert abs(res["hpp_per_unit"] - 332.5) < 0.5
    assert res["profit_per_unit"] > 0


# -------- Purchase -> Production -> Sale --------
def test_full_operations_flow(admin_headers, tapioka, gula, baso_aci, recipe):
    # 1. Purchase - buy 2 kg tapioka and 1 kg gula
    pbody = {
        "items": [
            {"material_id": tapioka["id"], "qty": 2, "unit": "kg", "price": 10500, "discount": 0},
            {"material_id": gula["id"], "qty": 1, "unit": "kg", "price": 15500, "discount": 0},
        ],
        "payment_method": "Tunai", "payment_status": "paid",
    }
    r = requests.post(f"{API}/purchases", json=pbody, headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    pur = r.json()
    assert pur["total"] == 2 * 10500 + 15500  # 36500

    # Verify stock updated (gram)
    r = requests.get(f"{API}/materials/{tapioka['id']}", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["stock"] == pytest.approx(2000)  # 2 kg -> 2000 g

    # 2. Production: 1 batch produces 20 cups (per recipe)
    prod_body = {
        "product_id": baso_aci["id"], "recipe_id": recipe["id"],
        "batch_count": 1, "qty_produced": 20,
    }
    r = requests.post(f"{API}/production", json=prod_body, headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    prod = r.json()
    assert prod["qty_produced"] == 20
    assert prod["hpp_per_unit"] > 0

    # Verify product stock = 20
    r = requests.get(f"{API}/products/{baso_aci['id']}", headers=admin_headers, timeout=15)
    assert r.json()["stock"] == pytest.approx(20)

    # 3. Sale of 5 cups at 12000
    sbody = {
        "channel": "Offline", "payment_method": "Tunai",
        "items": [{"product_id": baso_aci["id"], "qty": 5, "price": 12000, "discount": 0}],
    }
    r = requests.post(f"{API}/sales", json=sbody, headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    sale = r.json()
    assert sale["net_total"] == 60000
    assert sale["items"][0]["hpp_unit"] > 0

    # Verify product stock decremented
    r = requests.get(f"{API}/products/{baso_aci['id']}", headers=admin_headers, timeout=15)
    assert r.json()["stock"] == pytest.approx(15)


def test_reports_load(admin_headers):
    for path in ("/reports/profit-loss", "/reports/sales", "/reports/cash-flow",
                 "/reports/purchases", "/reports/hpp", "/dashboard",
                 "/dashboard/material-cost-trend", "/alerts/stock"):
        r = requests.get(f"{API}{path}", headers=admin_headers, timeout=20)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


# -------- Demo seed --------
def test_demo_seed_and_delete(admin_headers):
    # Check status first; if demo exists delete
    st = requests.get(f"{API}/demo/status", headers=admin_headers, timeout=15).json()
    if st.get("has_demo"):
        requests.delete(f"{API}/demo", headers=admin_headers, timeout=60)
    r = requests.post(f"{API}/demo/seed", headers=admin_headers, timeout=60)
    assert r.status_code == 200, r.text
    st = requests.get(f"{API}/demo/status", headers=admin_headers, timeout=15).json()
    assert st["has_demo"] is True
    r = requests.delete(f"{API}/demo", headers=admin_headers, timeout=60)
    assert r.status_code == 200, r.text
    st = requests.get(f"{API}/demo/status", headers=admin_headers, timeout=15).json()
    assert st["has_demo"] is False


# -------- Data isolation between businesses --------
def test_register_and_isolation(tapioka, admin_headers):
    email = f"test_iso_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "name": "Iso User", "email": email, "password": "secret123", "business_name": "Iso Biz",
    }, timeout=20)
    assert r.status_code == 200, r.text
    token2 = r.json()["token"]

    # Second account material list should NOT contain admin's tapioka
    r = requests.get(f"{API}/materials", headers={"Authorization": f"Bearer {token2}"}, timeout=15)
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert tapioka["id"] not in ids, "data isolation broken: second account sees admin material"

    # And admin's material GET by id under second account must 404
    r = requests.get(f"{API}/materials/{tapioka['id']}",
                     headers={"Authorization": f"Bearer {token2}"}, timeout=15)
    assert r.status_code == 404


# -------- Cleanup --------
@pytest.fixture(scope="module", autouse=True)
def _cleanup(request, admin_headers):
    yield
    # Best effort clean; not critical
    try:
        mats = requests.get(f"{API}/materials?q=TEST_", headers=admin_headers, timeout=15).json()
        for m in mats:
            requests.delete(f"{API}/materials/{m['id']}", headers=admin_headers, timeout=15)
        prods = requests.get(f"{API}/products?q=TEST_", headers=admin_headers, timeout=15).json()
        for p in prods:
            requests.delete(f"{API}/products/{p['id']}", headers=admin_headers, timeout=15)
    except Exception:
        pass
