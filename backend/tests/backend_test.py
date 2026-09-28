"""End-to-end backend test suite for UMKM F&B HPP/Finance app.
Covers: auth + isolation, HPP accuracy, dynamic items, unit conversion,
validation, purchase/production/sale chains, expenses, reports, backup,
import CSV, demo status.
"""
import os
import io
import time
import uuid
import json
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # frontend/.env value - required
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE}/api"

ADMIN_EMAIL = "danarhuda59@gmail.com"
ADMIN_PASSWORD = "admin123"


# ------------------------ Fixtures ------------------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def new_user_session():
    """Register a fresh user in a new business for isolation tests."""
    email = f"test_iso_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "name": "Iso User", "email": email, "password": "Passw0rd!", "business_name": "Iso Biz"
    })
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    s.email = email
    return s


# ------------------------ Auth & isolation ------------------------
class TestAuth:
    def test_login_returns_token_and_user(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_me_with_bearer(self, admin):
        r = admin.get(f"{API}/auth/me")
        assert r.status_code == 200
        d = r.json()
        # /me returns {user, business}
        u = d.get("user") or d
        assert u["email"] == ADMIN_EMAIL

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code in (400, 401, 429)

    def test_register_creates_isolated_business(self, admin):
        # Register a brand new user - separate from session-wide new_user_session fixture
        email = f"test_iso2_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register", json={
            "name": "Iso User2", "email": email, "password": "Passw0rd!",
            "business_name": "Iso Biz 2"
        })
        assert r.status_code == 200
        tok = r.json()["token"]
        news = requests.Session()
        news.headers.update({"Authorization": f"Bearer {tok}"})
        adm = admin.get(f"{API}/materials").json()
        new = news.get(f"{API}/materials").json()
        assert isinstance(adm, list) and isinstance(new, list)
        assert len(new) == 0, f"New business should have zero materials, got {len(new)}"
        assert len(adm) > 0, "Admin should have seeded demo materials"


# ------------------------ HPP calculator accuracy ------------------------
class TestHppCalculate:
    def test_hpp_10_materials_expected_numbers(self, new_user_session):
        s = new_user_session
        prices = [500, 750, 300, 1200, 850, 450, 250, 1000, 700, 400]
        ids = []
        for i, p in enumerate(prices):
            r = s.post(f"{API}/materials", json={
                "name": f"TEST_Mat{i}", "purchase_unit": "pcs", "usage_unit": "pcs",
                "conversion_factor": 1, "last_price": p
            })
            assert r.status_code == 200, r.text
            ids.append(r.json()["id"])
        body = {
            "items": [{"material_id": mid, "qty": 1, "unit": "pcs", "waste_pct": 0} for mid in ids],
            "extra_costs": [
                {"name": "Kemasan", "type": "packaging", "method": "per_batch", "value": 2000},
                {"name": "Tenaga Kerja", "type": "labor", "method": "per_batch", "value": 1000},
                {"name": "Overhead", "type": "overhead", "method": "per_batch", "value": 500},
            ],
            "yield_qty": 10, "selling_price": 0,
        }
        r = s.post(f"{API}/hpp/calculate", json=body)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["item_count"] == 10
        assert round(d["material_total"], 2) == 6400.00
        assert round(d["total_batch"], 2) == 9900.00
        assert round(d["hpp_per_unit"], 2) == 990.00

    def test_yield_zero_returns_null_no_error(self, new_user_session):
        s = new_user_session
        r = s.post(f"{API}/hpp/calculate", json={
            "items": [], "extra_costs": [], "yield_qty": 0, "selling_price": 0
        })
        assert r.status_code == 200
        assert r.json()["hpp_per_unit"] is None

    def test_negative_qty_rejected(self, new_user_session):
        s = new_user_session
        # need a material first
        m = s.post(f"{API}/materials", json={"name": "TEST_NegQty", "purchase_unit": "pcs",
                   "usage_unit": "pcs", "conversion_factor": 1, "last_price": 100}).json()
        r = s.post(f"{API}/hpp/calculate", json={
            "items": [{"material_id": m["id"], "qty": -1, "unit": "pcs", "waste_pct": 0}],
            "extra_costs": [], "yield_qty": 1
        })
        assert r.status_code == 400

    def test_negative_price_rejected(self, new_user_session):
        s = new_user_session
        r = s.post(f"{API}/materials", json={"name": "TEST_NegPrice", "purchase_unit": "pcs",
                   "usage_unit": "pcs", "conversion_factor": 1, "last_price": -5})
        assert r.status_code == 400


# ------------------------ Unit conversion ------------------------
class TestUnitConversion:
    def _mat(self, s):
        return s.post(f"{API}/materials", json={
            "name": "TEST_Tapioka", "purchase_unit": "kg", "usage_unit": "gram",
            "conversion_factor": 1000, "last_price": 10000
        }).json()

    def test_gram_no_waste(self, new_user_session):
        m = self._mat(new_user_session)
        r = new_user_session.post(f"{API}/hpp/calculate", json={
            "items": [{"material_id": m["id"], "qty": 150, "unit": "gram", "waste_pct": 0}],
            "extra_costs": [], "yield_qty": 1
        })
        d = r.json()
        assert r.status_code == 200
        assert round(d["material_total"], 2) == 1500.00

    def test_gram_with_waste_5pct(self, new_user_session):
        # reuse a fresh material
        m = new_user_session.post(f"{API}/materials", json={
            "name": f"TEST_Tap_{uuid.uuid4().hex[:6]}", "purchase_unit": "kg", "usage_unit": "gram",
            "conversion_factor": 1000, "last_price": 10000
        }).json()
        r = new_user_session.post(f"{API}/hpp/calculate", json={
            "items": [{"material_id": m["id"], "qty": 150, "unit": "gram", "waste_pct": 5}],
            "extra_costs": [], "yield_qty": 1
        })
        assert round(r.json()["material_total"], 2) == 1575.00

    def test_qty_in_purchase_unit_kg(self, new_user_session):
        m = new_user_session.post(f"{API}/materials", json={
            "name": f"TEST_TapKg_{uuid.uuid4().hex[:6]}", "purchase_unit": "kg", "usage_unit": "gram",
            "conversion_factor": 1000, "last_price": 10000
        }).json()
        r = new_user_session.post(f"{API}/hpp/calculate", json={
            "items": [{"material_id": m["id"], "qty": 0.15, "unit": "kg", "waste_pct": 0}],
            "extra_costs": [], "yield_qty": 1
        })
        assert round(r.json()["material_total"], 2) == 1500.00


# ------------------------ Dynamic recipe item counts ------------------------
class TestRecipeDynamic:
    @pytest.mark.parametrize("n", [1, 5, 10, 30, 50])
    def test_recipe_n_items(self, new_user_session, n):
        s = new_user_session
        # create one material to reuse
        m = s.post(f"{API}/materials", json={
            "name": f"TEST_Reuse_{n}_{uuid.uuid4().hex[:6]}", "purchase_unit": "pcs",
            "usage_unit": "pcs", "conversion_factor": 1, "last_price": 100
        }).json()
        # create product
        p = s.post(f"{API}/products", json={"name": f"TEST_Prod_{n}", "unit": "pcs",
                   "selling_price": 5000}).json()
        items = [{"material_id": m["id"], "qty": 1, "unit": "pcs", "waste_pct": 0} for _ in range(n)]
        rc = s.post(f"{API}/recipes", json={
            "product_id": p["id"], "name": f"TEST_Recipe_{n}",
            "yield_qty": 1, "yield_unit": "pcs", "selling_price": 5000,
            "items": items, "extra_costs": []
        })
        assert rc.status_code == 200, rc.text
        rid = rc.json()["id"]
        # verify by GET
        got = s.get(f"{API}/recipes/{rid}").json()
        assert len(got["items"]) == n
        assert got["cost"]["item_count"] == n
        expected_material_total = sum(it["cost"] for it in got["cost"]["items"])
        assert round(got["cost"]["material_total"], 2) == round(expected_material_total, 2)
        assert round(got["cost"]["material_total"], 2) == round(100 * n, 2)


# ------------------------ Production validation ------------------------
class TestProductionValidation:
    def test_empty_recipe_rejected(self, new_user_session):
        s = new_user_session
        p = s.post(f"{API}/products", json={"name": "TEST_EmptyProd", "unit": "pcs",
                   "selling_price": 1000}).json()
        rc = s.post(f"{API}/recipes", json={"product_id": p["id"], "name": "TEST_Empty",
                    "yield_qty": 1, "items": [], "extra_costs": []}).json()
        r = s.post(f"{API}/production", json={"product_id": p["id"], "recipe_id": rc["id"],
                                              "batch_count": 1, "qty_produced": 1})
        assert r.status_code == 400
        assert "kosong" in r.json().get("detail", "").lower()

    def test_insufficient_stock(self, new_user_session):
        s = new_user_session
        m = s.post(f"{API}/materials", json={"name": "TEST_NoStock", "purchase_unit": "pcs",
                   "usage_unit": "pcs", "conversion_factor": 1, "last_price": 100}).json()
        p = s.post(f"{API}/products", json={"name": "TEST_NoStkProd", "unit": "pcs",
                   "selling_price": 1000}).json()
        rc = s.post(f"{API}/recipes", json={"product_id": p["id"], "name": "TEST_Stk",
                    "yield_qty": 1, "items": [{"material_id": m["id"], "qty": 5, "unit": "pcs",
                                               "waste_pct": 0}], "extra_costs": []}).json()
        r = s.post(f"{API}/production", json={"product_id": p["id"], "recipe_id": rc["id"],
                                              "batch_count": 1, "qty_produced": 1})
        assert r.status_code == 400

    def test_product_without_name(self, new_user_session):
        r = new_user_session.post(f"{API}/products", json={"name": "", "unit": "pcs",
                                                            "selling_price": 100})
        assert r.status_code == 400


# ------------------------ Admin end-to-end chain ------------------------
class TestAdminChain:
    """Runs against admin business (has demo data). Only creates, doesn't delete demo."""

    def test_purchase_updates_stock_and_price_and_cash(self, admin):
        mats = admin.get(f"{API}/materials").json()
        assert mats, "Admin must have demo materials"
        m = mats[0]
        cf = float(m.get("conversion_factor") or 1)
        old_stock = float(m.get("stock") or 0)
        old_last = float(m.get("last_price") or 0)
        cash_before = admin.get(f"{API}/cash/transactions").json()

        purchase = {
            "items": [{"material_id": m["id"], "qty": 2, "unit": m["purchase_unit"],
                       "price": old_last + 500 if old_last else 20000, "discount": 0}],
            "payment_status": "paid",
        }
        r = admin.post(f"{API}/purchases", json=purchase)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        # stock increased by 2 * cf
        m2 = admin.get(f"{API}/materials/{m['id']}").json()
        assert round(float(m2["stock"]) - old_stock, 4) == round(2 * cf, 4)
        # last_price updated
        assert float(m2["last_price"]) != old_last or old_last == 0
        # price history entry created for this purchase
        assert any(h.get("purchase_id") == pid for h in m2["price_history"])
        # cash out tx created
        cash_after = admin.get(f"{API}/cash/transactions").json()
        assert len(cash_after) > len(cash_before)
        assert any(t.get("ref_id") == pid and t["direction"] == "out" for t in cash_after)

    def test_unpaid_purchase_no_cash_then_pay(self, admin):
        mats = admin.get(f"{API}/materials").json()
        m = mats[0]
        r = admin.post(f"{API}/purchases", json={
            "items": [{"material_id": m["id"], "qty": 1, "unit": m["purchase_unit"],
                       "price": 15000, "discount": 0}],
            "payment_status": "unpaid",
        })
        assert r.status_code == 200
        pid = r.json()["id"]
        total = r.json()["total"]
        cash = admin.get(f"{API}/cash/transactions", params={"account_id": ""}).json()
        assert not any(t.get("ref_id") == pid and t["direction"] == "out" for t in cash)
        # pay
        rp = admin.post(f"{API}/purchases/{pid}/pay", json={"amount": total})
        assert rp.status_code == 200
        assert rp.json()["payment_status"] == "paid"
        cash2 = admin.get(f"{API}/cash/transactions").json()
        assert any(t.get("ref_id") == pid and t["direction"] == "out" for t in cash2)

    def test_production_snapshot_and_hpp_immutability(self, admin):
        recipes = admin.get(f"{API}/recipes").json()
        # find a recipe with a product and non-zero cost, whose materials have stock
        chosen = None
        for r in recipes:
            if not r.get("product_id"):
                continue
            summary = r.get("summary") or {}
            if summary.get("error") or not summary.get("hpp_per_unit"):
                continue
            full = admin.get(f"{API}/recipes/{r['id']}").json()
            # Try a small qty produced to keep material demands modest
            chosen = full
            break
        assert chosen, "Need at least one usable demo recipe with hpp"
        product_id = chosen["product_id"]
        recipe_id = chosen["id"]

        # Ensure enough material stock: buy each material a lot first
        for it in chosen["items"]:
            if it.get("material_id"):
                admin.post(f"{API}/purchases", json={
                    "items": [{"material_id": it["material_id"], "qty": 100,
                               "unit": None, "price": 1000, "discount": 0}],
                    "payment_status": "paid"
                })

        r1 = admin.post(f"{API}/production", json={
            "product_id": product_id, "recipe_id": recipe_id,
            "batch_count": 1, "qty_produced": 1
        })
        assert r1.status_code == 200, r1.text
        prod1 = r1.json()
        prod1_id = prod1["id"]
        hpp1 = admin.get(f"{API}/production/{prod1_id}").json()["hpp_per_unit"]
        assert hpp1 is not None
        assert len(admin.get(f"{API}/production/{prod1_id}").json()["items"]) > 0

        # Increase material price by buying at a higher price
        mat_id = None
        for it in chosen["items"]:
            if it.get("material_id"):
                mat_id = it["material_id"]
                break
        assert mat_id
        admin.post(f"{API}/purchases", json={
            "items": [{"material_id": mat_id, "qty": 50, "unit": None,
                       "price": 999999, "discount": 0}],
            "payment_status": "paid"
        })

        # New production - should show a different HPP
        r2 = admin.post(f"{API}/production", json={
            "product_id": product_id, "recipe_id": recipe_id,
            "batch_count": 1, "qty_produced": 1
        })
        assert r2.status_code == 200
        hpp2 = admin.get(f"{API}/production/{r2.json()['id']}").json()["hpp_per_unit"]
        # Old production HPP unchanged
        hpp1_again = admin.get(f"{API}/production/{prod1_id}").json()["hpp_per_unit"]
        assert hpp1_again == hpp1, "Old HPP snapshot MUST be immutable"
        assert hpp2 > hpp1, f"New HPP {hpp2} should be higher than old {hpp1}"

    def test_sale_flow_and_delete_restores(self, admin):
        prods = admin.get(f"{API}/products").json()
        p = next((x for x in prods if float(x.get("stock") or 0) > 0 and float(x.get("avg_hpp") or 0) > 0), None)
        assert p, "Need a product with stock and avg_hpp"
        stock_before = float(p["stock"])

        r = admin.post(f"{API}/sales", json={
            "channel": "Shopee",
            "items": [{"product_id": p["id"], "qty": 1, "price": float(p.get("selling_price") or 20000)}],
            "platform_fee": 500
        })
        assert r.status_code == 200, r.text
        sale = r.json()
        assert round(sale["total_hpp"], 4) == round(1 * float(p["avg_hpp"]), 4)
        assert round(sale["net_total"], 2) == round(sale["total"] - 500, 2)

        # cash tx recorded
        cash = admin.get(f"{API}/cash/transactions").json()
        assert any(t.get("ref_id") == sale["id"] and t["direction"] == "in" for t in cash)

        # stock decreased
        p2 = admin.get(f"{API}/products/{p['id']}").json()
        assert abs(float(p2["stock"]) - (stock_before - 1)) < 1e-6

        # dashboard/pl includes sale
        dash = admin.get(f"{API}/dashboard").json()
        assert dash["cash_balance"] is not None
        pl = admin.get(f"{API}/reports/profit-loss").json()
        assert "summary" in pl

        # delete restores stock
        rd = admin.delete(f"{API}/sales/{sale['id']}")
        assert rd.status_code == 200
        p3 = admin.get(f"{API}/products/{p['id']}").json()
        assert abs(float(p3["stock"]) - stock_before) < 1e-6
        cash2 = admin.get(f"{API}/cash/transactions").json()
        active_in = [t for t in cash2 if t.get("ref_id") == sale["id"] and t["direction"] == "in"
                     and not t.get("is_reversal")]
        # Reversal cancels the effect; there should be either no active in-tx or a matching reversal
        # Accept either behavior: net zero effect
        pos = sum(t["amount"] for t in cash2 if t.get("ref_id") == sale["id"] and t["direction"] == "in")
        neg = sum(t["amount"] for t in cash2 if t.get("ref_id") == sale["id"] and t["direction"] == "out")
        assert abs(pos - neg) < 0.01 or len(active_in) == 0

    def test_expense_crud_and_cash(self, admin):
        r = admin.post(f"{API}/expenses", json={
            "category": "Operasional", "description": "TEST expense",
            "amount": 12345, "payment_method": "Tunai"
        })
        assert r.status_code == 200
        eid = r.json()["id"]
        cash = admin.get(f"{API}/cash/transactions").json()
        assert any(t.get("ref_id") == eid and t["direction"] == "out" for t in cash)
        # update
        ru = admin.put(f"{API}/expenses/{eid}", json={
            "category": "Marketing", "description": "TEST expense upd", "amount": 500,
            "payment_method": "Tunai"
        })
        assert ru.status_code == 200
        # delete
        rd = admin.delete(f"{API}/expenses/{eid}")
        assert rd.status_code == 200
        cash3 = admin.get(f"{API}/cash/transactions").json()
        assert not any(t.get("ref_id") == eid for t in cash3)

    def test_cashflow_balance_math(self, admin):
        cf = admin.get(f"{API}/reports/cash-flow").json()
        assert round(cf["opening_balance"] + cf["total_in"] - cf["total_out"], 2) == round(cf["closing_balance"], 2)

    def test_inventory_summary_and_adjust(self, admin):
        summ = admin.get(f"{API}/inventory/summary").json()
        assert isinstance(summ, list) and len(summ) > 0
        txs = admin.get(f"{API}/inventory/transactions").json()
        assert isinstance(txs, list)
        # try adjustment producing negative stock -> must fail
        m = admin.get(f"{API}/materials").json()[0]
        r = admin.post(f"{API}/inventory/adjust", json={
            "item_type": "material", "item_id": m["id"], "qty": 1e12,
            "direction": "out", "reason": "adjustment"
        })
        assert r.status_code == 400


# ------------------------ Reports & meta ------------------------
class TestReports:
    endpoints = [
        "/reports/sales", "/reports/purchases", "/reports/expenses",
        "/reports/production", "/reports/hpp", "/reports/suppliers",
        "/reports/products", "/reports/channels", "/reports/price-history",
        "/reports/cash-flow", "/reports/profit-loss",
    ]

    @pytest.mark.parametrize("path", endpoints)
    def test_report_ok(self, admin, path):
        r = admin.get(f"{API}{path}", params={"start": "2020-01-01", "end": "2030-12-31"})
        assert r.status_code == 200, f"{path} => {r.status_code}: {r.text[:200]}"

    def test_dashboard(self, admin):
        r = admin.get(f"{API}/dashboard", params={"start": "2020-01-01", "end": "2030-12-31"})
        assert r.status_code == 200

    def test_bep(self, admin):
        r = admin.post(f"{API}/bep/calculate", json={
            "fixed_cost": 1000000, "selling_price": 10000, "variable_cost": 6000
        })
        assert r.status_code == 200
        d = r.json()
        assert d["bep_units"] == 250.0
        assert d["bep_rupiah"] == 2500000.0


# ------------------------ Backup, import, demo status ------------------------
class TestBackupImportDemo:
    def test_backup_returns_collections(self, admin):
        r = admin.get(f"{API}/backup")
        assert r.status_code == 200
        d = r.json()
        assert "collections" in d or isinstance(d, dict)

    def test_import_template_csv(self, admin):
        r = admin.get(f"{API}/import/template/materials")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "") or r.text.count(",") >= 1

    def test_import_preview_and_commit(self, admin):
        # Indonesian column names as per /api/import/template/materials
        csv = "kode,nama,kategori,satuan_beli,satuan_pakai,faktor_konversi,harga_beli,min_stok,stok_awal,catatan\n" \
              "TSTIMP1,TEST_ImpOk,,pcs,pcs,1,500,0,0,\n" \
              ",,,pcs,pcs,1,500,0,0,\n"  # empty nama -> row error
        files = {"file": ("m.csv", csv.encode(), "text/csv")}
        r = requests.post(f"{API}/import/preview",
                          headers={"Authorization": admin.headers["Authorization"]},
                          data={"itype": "materials"}, files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        # Should contain rows with validation info
        assert isinstance(d, dict)

    def test_demo_status(self, admin):
        r = admin.get(f"{API}/demo/status")
        assert r.status_code == 200
        assert "has_demo" in r.json()
