"""Automated HPP tests: 1, 5, 10, 30, 50 bahan + spec example (10 bahan = Rp6.400, total HPP Rp9.900, HPP/unit Rp990)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_hpp")
import pytest
from fastapi import HTTPException
from core import compute_hpp


def mat(i, price, cf=1, usage="pcs", purchase="pcs"):
    return {"id": f"m{i}", "name": f"Bahan {i}", "last_price": price, "conversion_factor": cf, "usage_unit": usage, "purchase_unit": purchase}


def run(costs, extras=None, yield_qty=10, selling=0):
    materials = {f"m{i}": mat(i, c) for i, c in enumerate(costs)}
    items = [{"material_id": f"m{i}", "qty": 1, "unit": "pcs", "waste_pct": 0} for i in range(len(costs))]
    return compute_hpp(items, extras or [], yield_qty, selling, materials, {})


def test_spec_example_10_items():
    costs = [500, 750, 300, 1200, 850, 450, 250, 1000, 700, 400]
    extras = [{"name": "Kemasan", "type": "packaging", "method": "per_batch", "value": 2000},
              {"name": "Tenaga kerja", "type": "labor", "method": "per_batch", "value": 1000},
              {"name": "Overhead", "type": "overhead", "method": "per_batch", "value": 500}]
    r = run(costs, extras, yield_qty=10)
    assert r["item_count"] == 10
    assert r["material_total"] == 6400
    assert r["total_batch"] == 9900
    assert r["hpp_per_unit"] == 990


@pytest.mark.parametrize("n", [1, 5, 10, 30, 50])
def test_dynamic_item_counts(n):
    costs = [100 * (i + 1) for i in range(n)]
    r = run(costs)
    assert r["item_count"] == n
    assert len(r["items"]) == n
    assert r["material_total"] == sum(costs)
    assert r["hpp_per_unit"] == sum(costs) / 10


def test_unit_conversion_and_waste():
    materials = {"m1": mat(1, 10000, cf=1000, usage="gram", purchase="kg")}
    r = compute_hpp([{"material_id": "m1", "qty": 150, "unit": "gram", "waste_pct": 0}], [], 1, 0, materials, {})
    assert r["items"][0]["unit_price"] == 10
    assert r["material_total"] == 1500
    r = compute_hpp([{"material_id": "m1", "qty": 150, "unit": "gram", "waste_pct": 5}], [], 1, 0, materials, {})
    assert r["material_total"] == 1575
    r = compute_hpp([{"material_id": "m1", "qty": 0.15, "unit": "kg", "waste_pct": 0}], [], 1, 0, materials, {})
    assert round(r["material_total"], 2) == 1500


def test_yield_recalculation_and_margin():
    materials = {"m1": mat(1, 500000)}
    items = [{"material_id": "m1", "qty": 1, "unit": "pcs", "waste_pct": 0}]
    assert compute_hpp(items, [], 100, 0, materials, {})["hpp_per_unit"] == 5000
    r = compute_hpp(items, [], 125, 6000, materials, {})
    assert r["hpp_per_unit"] == 4000
    assert r["profit_per_unit"] == 2000
    assert round(r["margin_pct"], 2) == 33.33
    assert r["markup_pct"] == 50


def test_zero_yield_no_division():
    r = run([1000], yield_qty=0)
    assert r["hpp_per_unit"] is None and r["warning"]


def test_negative_inputs_rejected():
    with pytest.raises(HTTPException):
        run([1000], yield_qty=-1)
    materials = {"m1": mat(1, 100)}
    with pytest.raises(HTTPException):
        compute_hpp([{"material_id": "m1", "qty": -5, "unit": "pcs", "waste_pct": 0}], [], 1, 0, materials, {})
    with pytest.raises(HTTPException):
        compute_hpp([{"material_id": "missing", "qty": 1, "unit": "pcs", "waste_pct": 0}], [], 1, 0, materials, {})


def test_extra_cost_methods():
    materials = {"m1": mat(1, 10000)}
    items = [{"material_id": "m1", "qty": 1, "unit": "pcs", "waste_pct": 0}]
    extras = [{"type": "overhead", "method": "per_unit", "value": 100}, {"type": "other", "method": "pct_material", "value": 10}, {"type": "packaging", "method": "per_batch", "value": 500}]
    r = compute_hpp(items, extras, 20, 0, materials, {})
    assert r["overhead_total"] == 2000 and r["other_total"] == 1000 and r["packaging_total"] == 500
    assert r["total_batch"] == 13500
