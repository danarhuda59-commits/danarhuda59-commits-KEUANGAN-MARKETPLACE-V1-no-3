"""Iteration 8: Partial refund per marketplace order line + include_marketplace_in_pl toggle."""
import os, io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
CRED = {"email": "admin@keuangan.com", "password": "Admin12345!"}


@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{API}/auth/login", json=CRED, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def product(auth):
    """Create product, run a purchase-like production to give initial stock + avg_hpp.
    Easier path: create material w/ initial_stock, product, recipe, production."""
    # Create/get category
    cat = requests.get(f"{API}/categories", headers=auth).json()
    cat_id = cat[0]["id"] if cat else None
    # material with initial stock
    m = requests.post(f"{API}/materials", headers=auth, json={
        "name": "TEST_IT8_Material", "purchase_unit": "kg", "usage_unit": "gram",
        "conversion_factor": 1000, "last_price": 10000, "initial_stock": 50000
    }).json()
    # product
    p = requests.post(f"{API}/products", headers=auth, json={
        "name": "TEST_IT8_Product", "sku": "TEST-IT8-SKU", "unit": "pcs", "selling_price": 20000
    }).json()
    # recipe: 100g per unit, cost per unit = 100 * (10000/1000) = 1000
    rec = requests.post(f"{API}/recipes", headers=auth, json={
        "product_id": p["id"], "name": "TEST_IT8_Recipe", "yield_qty": 1, "yield_unit": "pcs",
        "selling_price": 20000, "is_default": True,
        "items": [{"material_id": m["id"], "qty": 100, "unit": "gram", "waste_pct": 0}]
    })
    assert rec.status_code == 200, rec.text
    rec = rec.json()
    # production of 20 pcs
    prod = requests.post(f"{API}/production", headers=auth, json={
        "product_id": p["id"], "recipe_id": rec["id"], "batch_count": 1, "qty_produced": 20
    })
    assert prod.status_code == 200, prod.text
    # refetch product
    pr = [x for x in requests.get(f"{API}/products", headers=auth).json() if x["id"] == p["id"]][0]
    assert pr.get("stock", 0) >= 20, f"stock={pr.get('stock')}"
    assert (pr.get("avg_hpp") or 0) > 0, f"avg_hpp={pr.get('avg_hpp')}"
    return pr


def _stock(auth, pid):
    p = [x for x in requests.get(f"{API}/products", headers=auth).json() if x["id"] == pid][0]
    return p.get("stock", 0)


def test_create_order_qty4_refund1(auth, product):
    stock_before = _stock(auth, product["id"])
    body = {
        "order_id": "TEST_IT8_ORD_A", "channel": "Shopee", "product_id": product["id"],
        "qty": 4, "selling_price": 20000, "discount": 0, "voucher": 0, "refund_qty": 1,
        "status": "Selesai",
    }
    r = requests.post(f"{API}/marketplace/orders", headers=auth, json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    # refund auto = 1/4 of (20000*4 - 0 - 0) = 20000
    assert abs(d["refund"] - 20000) < 1, d["refund"]
    assert d["qty_net"] == 3
    assert abs(d["hpp_total"] - d["hpp_unit"] * 3) < 0.5
    assert abs(d["packaging_cost"] - d["packaging_cost_per_unit"] * 4) < 0.5
    # stock reduced by 3
    stock_after = _stock(auth, product["id"])
    assert stock_before - stock_after == 3, f"before={stock_before} after={stock_after}"
    pytest.oid_A = d["id"]


def test_update_refund_qty_2(auth, product):
    oid = pytest.oid_A
    stock_before = _stock(auth, product["id"])  # was reduced by 3
    body = {
        "order_id": "TEST_IT8_ORD_A", "channel": "Shopee", "product_id": product["id"],
        "qty": 4, "selling_price": 20000, "discount": 0, "voucher": 0,
        "refund": 40000, "refund_qty": 2, "status": "Selesai",
    }
    r = requests.put(f"{API}/marketplace/orders/{oid}", headers=auth, json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["qty_net"] == 2
    assert abs(d["refund"] - 40000) < 1
    assert abs(d["hpp_total"] - d["hpp_unit"] * 2) < 0.5
    # Net effect: total deducted = 2, previously 3 → stock should be +1 vs before
    stock_after = _stock(auth, product["id"])
    assert stock_after - stock_before == 1, f"delta={stock_after - stock_before}"


def test_status_dibatalkan_restores_stock(auth, product):
    oid = pytest.oid_A
    stock_before = _stock(auth, product["id"])
    r = requests.patch(f"{API}/marketplace/orders/{oid}/status", headers=auth, json={"status": "Dibatalkan"})
    assert r.status_code == 200, r.text
    stock_after = _stock(auth, product["id"])
    # Restore 2 units
    assert stock_after - stock_before == 2, f"delta={stock_after - stock_before}"


def test_refund_qty_greater_than_qty_400(auth, product):
    body = {
        "order_id": "TEST_IT8_BAD", "channel": "Shopee", "product_id": product["id"],
        "qty": 2, "selling_price": 15000, "refund_qty": 3, "status": "Selesai",
    }
    r = requests.post(f"{API}/marketplace/orders", headers=auth, json=body)
    assert r.status_code == 400, r.text


def test_dashboard_summary_net_qty(auth, product):
    # Create fresh order and check dashboard summary
    body = {
        "order_id": "TEST_IT8_DASH", "channel": "TikTok Shop", "product_id": product["id"],
        "qty": 5, "selling_price": 20000, "refund_qty": 2, "status": "Selesai",
    }
    r = requests.post(f"{API}/marketplace/orders", headers=auth, json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    # Query dashboard filtered by product+channel+date
    date = d["date"]
    r2 = requests.get(f"{API}/marketplace/dashboard", headers=auth,
                      params={"start": date, "end": date, "product_id": product["id"], "channel": "TikTok Shop"})
    assert r2.status_code == 200
    s = r2.json()["summary"]
    assert s["qty_sold"] >= 3  # net qty
    assert s["refund_qty"] >= 2
    assert s["partial_refund_count"] >= 1
    pytest.oid_dash = d["id"]


def test_include_marketplace_in_pl_toggle(auth, product):
    # Get current business
    biz = requests.get(f"{API}/business", headers=auth).json()
    original = biz.get("include_marketplace_in_pl")

    # Set to True
    biz_update = {**{k: biz.get(k, "") for k in ("name", "address", "phone", "email", "logo_url", "notes")},
                  "name": biz["name"], "target_margin": biz.get("target_margin", 30),
                  "include_marketplace_in_pl": True}
    r = requests.put(f"{API}/business", headers=auth, json=biz_update)
    assert r.status_code == 200, r.text
    assert r.json()["include_marketplace_in_pl"] is True

    # /api/reports/profit-loss - use wide date window
    r = requests.get(f"{API}/reports/profit-loss", headers=auth, params={"start": "2020-01-01", "end": "2099-12-31"})
    assert r.status_code == 200, r.text
    pl = r.json()
    assert pl.get("marketplace_included") is True
    assert pl.get("marketplace_summary") is not None
    # by_product should have marketplace_count > 0 somewhere
    assert any(row.get("marketplace_count", 0) > 0 for row in pl.get("by_product", [])), "no marketplace_count>0 in by_product"
    assert any(row.get("marketplace_count", 0) > 0 for row in pl.get("by_channel", [])), "no marketplace_count>0 in by_channel"

    # /api/reports/sales should include source='marketplace' rows
    r = requests.get(f"{API}/reports/sales", headers=auth, params={"start": "2020-01-01", "end": "2099-12-31"})
    assert r.status_code == 200
    sales = r.json().get("sales", [])
    assert any(s.get("source") == "marketplace" for s in sales), "no marketplace in sales"

    # Toggle off
    biz_update["include_marketplace_in_pl"] = False
    r = requests.put(f"{API}/business", headers=auth, json=biz_update)
    assert r.status_code == 200
    r = requests.get(f"{API}/reports/profit-loss", headers=auth, params={"start": "2020-01-01", "end": "2099-12-31"})
    pl2 = r.json()
    assert pl2.get("marketplace_included") is False
    assert pl2.get("marketplace_summary") is None

    # Restore original
    biz_update["include_marketplace_in_pl"] = bool(original)
    requests.put(f"{API}/business", headers=auth, json=biz_update)


def test_import_validate_refund_qty(auth, product):
    body = {
        "channel": "Shopee",
        "mapping": {"order_id": "Order ID", "qty": "Qty", "selling_price": "Harga",
                    "sku": "SKU", "status": "Status", "refund_qty": "Qty Retur"},
        "rows": [{
            "Order ID": "TEST_IT8_IMP_1", "Qty": "3", "Harga": "18000",
            "SKU": "TEST-IT8-SKU", "Status": "Selesai", "Qty Retur": "1"
        }],
        "default_status": "Selesai",
    }
    r = requests.post(f"{API}/marketplace/import/validate", headers=auth, json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    row0 = j["rows"][0]
    assert row0["data"]["refund_qty"] == 1.0, row0
    assert row0["data"]["qty"] == 3.0


def test_import_commit_refund_qty(auth, product):
    rows = [{
        "row": 2,
        "data": {
            "order_id": "TEST_IT8_IMP_COMMIT", "date": None, "qty": 3, "selling_price": 18000,
            "product_id": product["id"], "product_name": product["name"], "sku": product.get("sku") or "",
            "status": "Selesai", "refund_qty": 1, "customer": "", "notes": "",
        }
    }]
    r = requests.post(f"{API}/marketplace/import/commit", headers=auth,
                      json={"channel": "Shopee", "filename": "test.csv", "rows": rows})
    assert r.status_code == 200, r.text
    log = r.json()
    assert log["imported"] >= 1, log
    # Verify the order exists with refund_qty
    lst = requests.get(f"{API}/marketplace/orders", headers=auth, params={"q": "TEST_IT8_IMP_COMMIT"}).json()
    assert any(o["order_id"] == "TEST_IT8_IMP_COMMIT" and o.get("refund_qty") == 1 for o in lst), lst


def test_regression_no_refund_qty(auth, product):
    body = {
        "order_id": "TEST_IT8_REG", "channel": "Website", "product_id": product["id"],
        "qty": 2, "selling_price": 20000, "status": "Selesai",
    }
    r = requests.post(f"{API}/marketplace/orders", headers=auth, json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("refund_qty") == 0
    assert d["qty_net"] == 2


def test_regression_endpoints_200(auth):
    for path in ("/marketplace/fees", "/marketplace/packaging/items", "/marketplace/packaging/configs",
                 "/marketplace/settlements", "/marketplace/reconciliation", "/marketplace/meta"):
        r = requests.get(f"{API}{path}", headers=auth)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
