"""Full-stack backend regression test for iteration 7 (fresh import verification)."""
import os
import time
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # try reading frontend .env
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip().rstrip("/")
            break

ADMIN_EMAIL = "admin@keuangan.com"
ADMIN_PW = "Admin12345!"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Health & Auth ----------
def test_health():
    r = requests.get(f"{BASE}/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_bad():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_me(auth):
    r = requests.get(f"{BASE}/api/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == ADMIN_EMAIL


def test_register_new_user():
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE}/api/auth/register", json={
        "name": "TEST User", "email": email, "password": "secret1", "business_name": "TEST Biz"
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == email
    assert "token" in body


def test_change_password_wrong_old(auth):
    r = requests.post(f"{BASE}/api/auth/change-password", headers=auth,
                      json={"old_password": "wrong", "new_password": "newpass1"})
    assert r.status_code == 400


# ---------- Master ----------
def test_units_list(auth):
    r = requests.get(f"{BASE}/api/units", headers=auth)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_categories_and_suppliers(auth):
    r = requests.get(f"{BASE}/api/categories", headers=auth)
    assert r.status_code == 200
    r = requests.post(f"{BASE}/api/suppliers", headers=auth,
                      json={"name": f"TEST Supplier {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="session")
def material_id(auth):
    r = requests.post(f"{BASE}/api/materials", headers=auth, json={
        "name": f"TEST Bahan {uuid.uuid4().hex[:6]}",
        "purchase_unit": "kg", "usage_unit": "gram", "conversion_factor": 1000,
        "last_price": 10000, "min_stock": 100, "initial_stock": 5000
    })
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    # GET back
    g = requests.get(f"{BASE}/api/materials/{mid}", headers=auth)
    assert g.status_code == 200
    return mid


def test_material_created(material_id, auth):
    r = requests.get(f"{BASE}/api/materials/{material_id}", headers=auth)
    assert r.status_code == 200


@pytest.fixture(scope="session")
def product_id(auth):
    r = requests.post(f"{BASE}/api/products", headers=auth, json={
        "name": f"TEST Produk {uuid.uuid4().hex[:6]}", "unit": "pcs", "selling_price": 15000
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- Recipes / HPP ----------
def test_hpp_calculate(auth, material_id):
    r = requests.post(f"{BASE}/api/hpp/calculate", headers=auth, json={
        "items": [{"material_id": material_id, "qty": 100, "unit": "gram", "waste_pct": 0}],
        "extra_costs": [{"name": "Overhead", "type": "overhead", "method": "per_batch", "value": 500}],
        "yield_qty": 10, "selling_price": 5000
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert "hpp_per_unit" in d
    assert d["hpp_per_unit"] > 0


@pytest.fixture(scope="session")
def recipe_id(auth, material_id, product_id):
    r = requests.post(f"{BASE}/api/recipes", headers=auth, json={
        "product_id": product_id, "name": f"TEST Recipe {uuid.uuid4().hex[:6]}",
        "yield_qty": 10, "yield_unit": "pcs", "selling_price": 15000,
        "items": [{"material_id": material_id, "qty": 100, "unit": "gram", "waste_pct": 5}],
        "extra_costs": [{"name": "OH", "type": "overhead", "method": "per_batch", "value": 1000}]
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_recipe_get(auth, recipe_id):
    r = requests.get(f"{BASE}/api/recipes/{recipe_id}", headers=auth)
    assert r.status_code == 200
    d = r.json()
    assert d["cost"]["hpp_per_unit"] > 0


# ---------- Operations ----------
def test_purchase_creates_stock_and_cash(auth, material_id):
    r = requests.post(f"{BASE}/api/purchases", headers=auth, json={
        "items": [{"material_id": material_id, "qty": 2, "price": 12000}],
        "payment_status": "paid"
    })
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 24000


def test_production_and_sale(auth, product_id, recipe_id):
    # produce 5 units
    r = requests.post(f"{BASE}/api/production", headers=auth, json={
        "product_id": product_id, "recipe_id": recipe_id, "batch_count": 1, "qty_produced": 10
    })
    assert r.status_code == 200, r.text
    # sell 2
    r = requests.post(f"{BASE}/api/sales", headers=auth, json={
        "items": [{"product_id": product_id, "qty": 2, "price": 15000}]
    })
    assert r.status_code == 200, r.text
    assert r.json()["net_total"] == 30000


# ---------- Finance ----------
def test_cash_accounts(auth):
    r = requests.get(f"{BASE}/api/cash/accounts", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_expense_create(auth):
    r = requests.post(f"{BASE}/api/expenses", headers=auth, json={
        "category": "Operasional", "description": "TEST expense", "amount": 5000
    })
    assert r.status_code == 200


def test_dashboard(auth):
    r = requests.get(f"{BASE}/api/dashboard", headers=auth)
    assert r.status_code == 200
    d = r.json()
    assert "period" in d and "cash_balance" in d


def test_report_pl(auth):
    r = requests.get(f"{BASE}/api/reports/profit-loss", headers=auth)
    assert r.status_code == 200
    assert "summary" in r.json()


# ---------- Marketplace ----------
def test_marketplace_meta(auth):
    r = requests.get(f"{BASE}/api/marketplace/meta", headers=auth)
    assert r.status_code == 200
    assert "channels" in r.json()


def test_marketplace_fee_crud(auth):
    r = requests.post(f"{BASE}/api/marketplace/fees", headers=auth, json={
        "name": "TEST Admin Shopee", "channel": "Shopee", "category": "admin",
        "fee_type": "percent", "value": 5
    })
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    r = requests.delete(f"{BASE}/api/marketplace/fees/{fid}", headers=auth)
    assert r.status_code == 200


@pytest.fixture(scope="session")
def mp_order(auth, product_id):
    # need to produce stock first for the product
    r = requests.post(f"{BASE}/api/marketplace/orders", headers=auth, json={
        "order_id": f"TEST-{uuid.uuid4().hex[:8]}", "channel": "Shopee",
        "product_id": product_id, "qty": 1, "selling_price": 20000, "status": "Selesai"
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_marketplace_order_and_dashboard(auth, mp_order):
    r = requests.get(f"{BASE}/api/marketplace/orders", headers=auth)
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/marketplace/dashboard", headers=auth)
    assert r.status_code == 200
    assert "summary" in r.json()


def test_marketplace_settlement(auth, mp_order):
    r = requests.post(f"{BASE}/api/marketplace/settlements", headers=auth, json={
        "channel": "Shopee", "settlement_id": f"S-{uuid.uuid4().hex[:6]}",
        "order_id": mp_order["order_id"], "gross_sales": 20000, "marketplace_fee": 1000,
        "actual_payout": 19000
    })
    assert r.status_code == 200, r.text


def test_marketplace_reports(auth):
    r = requests.get(f"{BASE}/api/marketplace/reports/sales", headers=auth)
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/marketplace/reports/profit", headers=auth)
    assert r.status_code == 200
    r = requests.get(f"{BASE}/api/marketplace/reconciliation", headers=auth)
    assert r.status_code == 200


def test_marketplace_packaging(auth):
    r = requests.post(f"{BASE}/api/marketplace/packaging/items", headers=auth, json={
        "name": f"TEST Pouch {uuid.uuid4().hex[:6]}", "purchase_price": 5000,
        "purchase_qty": 100, "unit": "pcs"
    })
    assert r.status_code == 200, r.text
