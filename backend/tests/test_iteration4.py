"""Iteration 4 tests: target_margin auto-suggest price, HPP sub-recipe pct_material fix,
storage 503 upload, CORS strict origin, and /api/meta.storage_enabled=false."""
import math
import os
import io
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    envp = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    with open(envp) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE}/api"
ADMIN = {"email": "admin@keuangan.id", "password": "admin12345"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- Target margin: default + override ----------------
@pytest.fixture(scope="module")
def qa_material(H):
    # create material for recipe items
    body = {"name": "QA_TM_Tapioka", "purchase_unit": "kg", "usage_unit": "gram", "conversion_factor": 1000, "last_price": 10000}
    r = requests.post(f"{API}/materials", json=body, headers=H, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_business_default_target_margin_30(H):
    r = requests.get(f"{API}/business", headers=H, timeout=30)
    assert r.status_code == 200
    # ensure business.target_margin defaults to 30 (or set it explicitly)
    biz = r.json()
    if biz.get("target_margin") != 30:
        payload = {"name": biz.get("name") or "Usaha", "address": biz.get("address") or "",
                   "phone": biz.get("phone") or "", "email": biz.get("email") or "",
                   "logo_url": biz.get("logo_url") or "", "target_margin": 30, "notes": biz.get("notes") or ""}
        rr = requests.put(f"{API}/business", json=payload, headers=H, timeout=30)
        assert rr.status_code == 200


def test_create_recipe_no_margin_uses_business_default(H, qa_material):
    body = {
        "name": "QA_TM_Recipe_Default", "yield_qty": 10, "yield_unit": "pcs", "selling_price": 0,
        "items": [{"material_id": qa_material["id"], "qty": 1000, "unit": "gram", "waste_pct": 0}],
    }
    r = requests.post(f"{API}/recipes", json=body, headers=H, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    cost = d["cost"]
    hpp = cost["hpp_per_unit"]
    assert hpp == pytest.approx(1000.0)  # 1000g * (10000/1000) / 10 = 1000
    assert cost["target_margin_pct"] == 30
    assert cost["suggested_price"] == pytest.approx(hpp / 0.7, rel=1e-4)
    assert cost["suggested_price_rounded"] == math.ceil(cost["suggested_price"] / 100.0) * 100
    assert cost["suggested_profit_per_unit"] == pytest.approx(cost["suggested_price"] - hpp, rel=1e-4)
    assert isinstance(cost["suggestion_note"], str) and len(cost["suggestion_note"]) > 0
    pytest.recipe_default_id = d["id"]


def test_update_recipe_target_margin_50(H, qa_material):
    rid = pytest.recipe_default_id
    body = {
        "name": "QA_TM_Recipe_Default", "yield_qty": 10, "yield_unit": "pcs", "selling_price": 0,
        "target_margin": 50,
        "items": [{"material_id": qa_material["id"], "qty": 1000, "unit": "gram", "waste_pct": 0}],
    }
    r = requests.put(f"{API}/recipes/{rid}", json=body, headers=H, timeout=30)
    assert r.status_code == 200, r.text
    cost = r.json()["cost"]
    assert cost["target_margin_pct"] == 50
    hpp = cost["hpp_per_unit"]
    assert cost["suggested_price"] == pytest.approx(hpp / 0.5, rel=1e-4)


def test_update_recipe_invalid_margins(H, qa_material):
    rid = pytest.recipe_default_id
    for tm in (100, -1):
        body = {
            "name": "QA_TM_Recipe_Default", "yield_qty": 10, "yield_unit": "pcs", "selling_price": 0,
            "target_margin": tm,
            "items": [{"material_id": qa_material["id"], "qty": 1000, "unit": "gram", "waste_pct": 0}],
        }
        r = requests.put(f"{API}/recipes/{rid}", json=body, headers=H, timeout=30)
        assert r.status_code == 400, f"expected 400 for margin {tm} got {r.status_code}"
        assert "Target margin" in r.json().get("detail", "")


def test_business_margin_override_reflects_in_list(H, qa_material):
    # create recipe WITHOUT override so it should follow business default
    body = {
        "name": "QA_TM_Recipe_NoOverride", "yield_qty": 10, "yield_unit": "pcs", "selling_price": 0,
        "items": [{"material_id": qa_material["id"], "qty": 1000, "unit": "gram", "waste_pct": 0}],
    }
    r = requests.post(f"{API}/recipes", json=body, headers=H, timeout=30)
    assert r.status_code == 200
    no_override_id = r.json()["id"]

    # set business to 40
    biz = requests.get(f"{API}/business", headers=H, timeout=30).json()
    payload = {**{k: biz.get(k) or "" for k in ("name", "address", "phone", "email", "logo_url", "notes")}, "target_margin": 40}
    if not payload["name"]:
        payload["name"] = "Usaha Demo UMKM"
    r = requests.put(f"{API}/business", json=payload, headers=H, timeout=30)
    assert r.status_code == 200

    try:
        rows = requests.get(f"{API}/recipes", headers=H, timeout=30).json()
        by_id = {x["id"]: x for x in rows}
        assert by_id[no_override_id]["summary"]["target_margin_pct"] == 40
        assert by_id[no_override_id]["summary"]["suggested_price_rounded"] is not None
        # override recipe (50) should still be 50
        assert by_id[pytest.recipe_default_id]["summary"]["target_margin_pct"] == 50
    finally:
        payload["target_margin"] = 30
        requests.put(f"{API}/business", json=payload, headers=H, timeout=30)
    # cleanup
    requests.delete(f"{API}/recipes/{no_override_id}", headers=H, timeout=30)


def test_hpp_calculate_uses_business_default_and_override(H, qa_material):
    body = {
        "items": [{"material_id": qa_material["id"], "qty": 1000, "unit": "gram", "waste_pct": 0}],
        "yield_qty": 10, "selling_price": 0,
    }
    r = requests.post(f"{API}/hpp/calculate", json=body, headers=H, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["target_margin_pct"] == 30

    body["target_margin"] = 25
    r = requests.post(f"{API}/hpp/calculate", json=body, headers=H, timeout=30)
    d = r.json()
    assert d["target_margin_pct"] == 25
    assert d["suggested_price"] == pytest.approx(d["hpp_per_unit"] / 0.75, rel=1e-4)

    # Save calculation
    save_body = {**body, "name": "QA_TM_Calc", "target_margin": 25}
    r = requests.post(f"{API}/hpp/calculations", json=save_body, headers=H, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["suggested_price"] is not None
    cid = r.json()["id"]
    requests.delete(f"{API}/hpp/calculations/{cid}", headers=H, timeout=30)


# ---------------- HPP sub-recipe pct_material fix ----------------
def test_hpp_sub_recipe_pct_material_fix(H):
    # Materials
    mA = requests.post(f"{API}/materials", json={"name": "QA_SUB_A", "purchase_unit": "kg", "usage_unit": "gram", "conversion_factor": 1000, "last_price": 10000}, headers=H, timeout=30).json()
    mB = requests.post(f"{API}/materials", json={"name": "QA_SUB_B", "purchase_unit": "kg", "usage_unit": "gram", "conversion_factor": 1000, "last_price": 20000}, headers=H, timeout=30).json()

    # Purchase 10kg each so we have stock for production
    p1 = requests.post(f"{API}/purchases", json={"items": [{"material_id": mA["id"], "qty": 10, "unit": "kg", "price": 10000}, {"material_id": mB["id"], "qty": 10, "unit": "kg", "price": 20000}], "payment_method": "Tunai"}, headers=H, timeout=30)
    assert p1.status_code == 200, p1.text

    # Sub recipe: yield 1000 gram, 1000 gram of A, pct_material overhead 10%
    sub = requests.post(f"{API}/recipes", json={
        "name": "QA_SUB_Recipe", "is_sub_recipe": True, "yield_qty": 1000, "yield_unit": "gram",
        "items": [{"material_id": mA["id"], "qty": 1000, "unit": "gram", "waste_pct": 0}],
        "extra_costs": [{"name": "OH", "type": "overhead", "method": "pct_material", "value": 10}],
    }, headers=H, timeout=30)
    assert sub.status_code == 200, sub.text
    sub_j = sub.json()
    # sub hpp_per_unit: material 1000*10=10000, overhead 10% = 1000; total=11000/1000 = 11
    assert sub_j["cost"]["hpp_per_unit"] == pytest.approx(11.0, rel=1e-4), sub_j["cost"]

    # Parent product
    prod = requests.post(f"{API}/products", json={"name": "QA_SUB_Product_P", "unit": "pcs", "selling_price": 5000}, headers=H, timeout=30).json()

    # Parent recipe: yield 10, items sub 500 gram + B 1000 gram
    parent = requests.post(f"{API}/recipes", json={
        "product_id": prod["id"], "name": "QA_SUB_Parent", "yield_qty": 10, "yield_unit": "pcs", "selling_price": 0, "is_default": True,
        "items": [
            {"sub_recipe_id": sub_j["id"], "qty": 500, "unit": "gram", "waste_pct": 0},
            {"material_id": mB["id"], "qty": 1000, "unit": "gram", "waste_pct": 0},
        ],
    }, headers=H, timeout=30)
    assert parent.status_code == 200, parent.text
    p_cost = parent.json()["cost"]
    # sub contributes 500g * 11 = 5500; B: 1000*20 = 20000; total 25500 / 10 = 2550
    assert p_cost["hpp_per_unit"] == pytest.approx(2550.0, rel=1e-4), p_cost

    # Production: batch 1, qty 10 (must not consume more stock than we bought)
    prod_r = requests.post(f"{API}/production", json={
        "product_id": prod["id"], "recipe_id": parent.json()["id"], "batch_count": 1, "qty_produced": 10, "operator": "QA"
    }, headers=H, timeout=30)
    assert prod_r.status_code == 200, prod_r.text
    pj = prod_r.json()
    # hpp_per_unit stored
    assert pj.get("hpp_per_unit") == pytest.approx(2550.0, rel=1e-3), pj
    # overhead_total should be 500 (10% of 5000 sub material cost * factor), NOT 2500
    assert pj.get("overhead_total") == pytest.approx(500.0, rel=1e-3), pj


# ---------------- Storage 503 + /api/meta ----------------
def test_upload_returns_503_when_no_s3(H):
    files = {"file": ("test.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 100), "image/png")}
    r = requests.post(f"{API}/upload", files=files, headers=H, timeout=30)
    assert r.status_code == 503, f"expected 503, got {r.status_code} {r.text}"
    assert "S3_BUCKET" in r.text


def test_meta_storage_enabled_false(H):
    r = requests.get(f"{API}/meta", headers=H, timeout=30)
    assert r.status_code == 200
    assert r.json().get("storage_enabled") is False


# ---------------- CORS strict origin ----------------
def test_cors_allowed_origin_echoed():
    # OPTIONS preflight for /api/auth/login
    r = requests.options(f"{API}/auth/login", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }, timeout=30)
    ao = r.headers.get("access-control-allow-origin")
    assert ao == "http://localhost:3000", f"got {ao!r} status {r.status_code}"


def test_cors_disallowed_origin_no_header():
    r = requests.options(f"{API}/auth/login", headers={
        "Origin": "https://evil.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }, timeout=30)
    ao = r.headers.get("access-control-allow-origin")
    assert not ao or ao != "https://evil.com", f"disallowed origin was echoed: {ao}"
