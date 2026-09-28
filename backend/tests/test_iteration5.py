"""Iteration 5 regression tests for Keuangan-V1 imported repo.
Covers: health, auth (login/me), meta, materials/products/sales full flow.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://finance-onboard-2.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "owner@keuangan-v1.app"
ADMIN_PASSWORD = "3kpgWW63mV8onkZN"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["role"] == "owner"
    return data["token"]


@pytest.fixture(scope="module")
def auth(api, token):
    api.headers.update({"Authorization": f"Bearer {token}"})
    return api


# ---------- Health ----------
def test_health(api):
    r = api.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"
    assert j.get("database") == "ok"


def test_root(api):
    r = api.get(f"{BASE_URL}/api/")
    assert r.status_code == 200


# ---------- Auth ----------
def test_login_wrong_password(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpass!!"})
    assert r.status_code == 401


def test_auth_me(auth):
    r = auth.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "user" in j and "business" in j
    assert j["user"]["email"] == ADMIN_EMAIL


# ---------- Meta ----------
def test_meta_channels(auth):
    r = auth.get(f"{BASE_URL}/api/meta")
    assert r.status_code == 200
    j = r.json()
    assert j.get("storage_enabled") is False
    names = j.get("channels", [])
    for expected in ["Shopee", "TikTok Shop", "Tokopedia", "Website"]:
        assert expected in names, f"Missing channel: {expected}, got {names}"


# ---------- Regression full flow ----------
@pytest.fixture(scope="module")
def created_ids():
    return {}


def test_create_material(auth, created_ids):
    payload = {
        "name": "TEST_Material_it5",
        "purchase_unit": "kg",
        "usage_unit": "g",
        "conversion_factor": 1000,
        "last_price": 50000,
        "min_stock": 0,
    }
    r = auth.post(f"{BASE_URL}/api/materials", json=payload)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["name"] == payload["name"]
    assert "id" in m
    created_ids["material_id"] = m["id"]


def test_create_product(auth, created_ids):
    payload = {"name": "TEST_Product_it5", "unit": "pcs", "selling_price": 25000}
    r = auth.post(f"{BASE_URL}/api/products", json=payload)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == payload["name"]
    created_ids["product_id"] = p["id"]


def test_cash_account_exists(auth, created_ids):
    r = auth.get(f"{BASE_URL}/api/cash/accounts")
    assert r.status_code == 200
    accs = r.json()
    # accounts may be dict of {accounts: [...]} or list
    if isinstance(accs, dict):
        accs = accs.get("accounts", accs.get("data", []))
    assert isinstance(accs, list) and len(accs) > 0, f"No cash account: {accs}"
    created_ids["cash_account_id"] = accs[0]["id"]


def test_inventory_adjust_add_product_stock(auth, created_ids):
    body = {
        "item_type": "product",
        "item_id": created_ids["product_id"],
        "qty": 10,
        "direction": "in",
        "reason": "adjustment",
        "note": "TEST_seed_stock",
    }
    r = auth.post(f"{BASE_URL}/api/inventory/adjust", json=body)
    assert r.status_code == 200, r.text

    # verify stock now = 10
    r2 = auth.get(f"{BASE_URL}/api/products/{created_ids['product_id']}")
    assert r2.status_code == 200
    assert float(r2.json().get("stock") or 0) == 10.0


def test_create_sale(auth, created_ids):
    body = {
        "channel": "Offline",
        "items": [{"product_id": created_ids["product_id"], "qty": 3, "price": 25000, "discount": 0}],
        "cash_account_id": created_ids["cash_account_id"],
        "payment_method": "Tunai",
    }
    r = auth.post(f"{BASE_URL}/api/sales", json=body)
    assert r.status_code == 200, r.text
    s = r.json()
    assert "net_total" in s and "total_hpp" in s and "profit" in s
    assert s["net_total"] == 75000
    created_ids["sale_id"] = s["id"]

    # verify product stock decreased to 7
    r2 = auth.get(f"{BASE_URL}/api/products/{created_ids['product_id']}")
    assert r2.status_code == 200
    assert float(r2.json().get("stock") or 0) == 7.0


def test_zzz_cleanup(auth, created_ids):
    # delete sale
    if "sale_id" in created_ids:
        r = auth.delete(f"{BASE_URL}/api/sales/{created_ids['sale_id']}")
        assert r.status_code == 200
    if "product_id" in created_ids:
        r = auth.delete(f"{BASE_URL}/api/products/{created_ids['product_id']}")
        assert r.status_code == 200
    if "material_id" in created_ids:
        r = auth.delete(f"{BASE_URL}/api/materials/{created_ids['material_id']}")
        assert r.status_code == 200
