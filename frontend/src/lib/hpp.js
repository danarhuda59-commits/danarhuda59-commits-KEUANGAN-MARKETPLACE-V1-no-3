const n = (v) => {
  const f = parseFloat(v);
  return Number.isFinite(f) ? f : 0;
};

export function convertToUsage(qty, unit, m, conv) {
  if (!unit || unit === m.usage_unit) return { qty, ok: true };
  const cf = n(m.conversion_factor);
  if (unit === m.purchase_unit && cf > 0) return { qty: qty * cf, ok: true };
  const f = conv[`${unit}>${m.usage_unit}`];
  if (f) return { qty: qty * f, ok: true };
  const f2 = conv[`${m.usage_unit}>${unit}`];
  if (f2) return { qty: qty / f2, ok: true };
  return { qty: 0, ok: false, error: `Konversi ${unit} → ${m.usage_unit} tidak ditemukan` };
}

export function suggestPrice(hpp, targetMargin) {
  if (targetMargin === null || targetMargin === undefined || targetMargin === "") return { target_margin_pct: null, suggested_price: null, suggested_price_rounded: null, suggested_profit_per_unit: null, suggestion_note: null };
  const tm = n(targetMargin);
  const out = { target_margin_pct: tm, suggested_price: null, suggested_price_rounded: null, suggested_profit_per_unit: null, suggestion_note: null };
  if (hpp === null || hpp === undefined) return out;
  if (tm < 0 || tm >= 100) return { ...out, suggestion_note: "Target margin harus antara 0 dan 99,99%" };
  const price = hpp / (1 - tm / 100);
  const sim = [...new Set([20, 30, 40, 50, tm])].sort((a, b) => a - b).map((m) => { const p = hpp / (1 - m / 100); return { margin_pct: m, price: p, price_rounded: p > 0 ? Math.ceil(p / 100) * 100 : 0, profit_per_unit: p - hpp, is_target: m === tm }; });
  return { ...out, suggested_price: price, suggested_price_rounded: price > 0 ? Math.ceil(price / 100) * 100 : 0, suggested_profit_per_unit: price - hpp, suggestion_note: `Harga saran = HPP ÷ (1 − ${tm}%)`, price_simulation: sim };
}

export function computeHpp({ items = [], extra_costs = [], yield_qty = 0, selling_price = 0, target_margin = null }, materials, conv, subCosts = {}, defaultMargin = null) {
  const rows = [];
  let materialTotal = 0;
  items.forEach((it, idx) => {
    const qty = Math.max(n(it.qty), 0);
    const waste = Math.max(n(it.waste_pct), 0);
    let row = { no: idx + 1, quantity: qty, waste_pct: waste, unit: it.unit, error: null, unit_price: 0, base_price: 0, conversion_factor: 1, qty_base: qty, cost: 0 };
    if (it.sub_recipe_id) {
      const sub = subCosts[it.sub_recipe_id];
      if (!sub) row.error = "Sub-resep tidak ditemukan";
      else { row.unit_price = n(sub.hpp_per_unit); row.base_price = row.unit_price; row.material_name = `[Sub] ${sub.name}`; row.unit = it.unit || sub.yield_unit; }
    } else {
      const m = materials[it.material_id];
      if (!m) row.error = "Bahan belum dipilih";
      else {
        const cf = n(m.conversion_factor);
        const unit = it.unit || m.usage_unit;
        const c = convertToUsage(qty, unit, m, conv);
        if (!c.ok) row.error = c.error;
        else if (cf <= 0) row.error = "Faktor konversi bahan harus > 0";
        else { row.qty_base = c.qty; row.unit_price = n(m.last_price) / cf; row.base_price = n(m.last_price); row.conversion_factor = cf; row.unit = unit; row.material_name = m.name; }
      }
    }
    if (!row.error) { row.cost = row.qty_base * row.unit_price * (1 + waste / 100); materialTotal += row.cost; }
    rows.push(row);
  });
  const y = Math.max(n(yield_qty), 0);
  const sums = { packaging: 0, labor: 0, overhead: 0, other: 0 };
  extra_costs.forEach((c) => {
    const v = Math.max(n(c.value), 0);
    const amt = c.method === "per_unit" ? v * y : c.method === "pct_material" ? (materialTotal * v) / 100 : v;
    sums[sums[c.type] !== undefined ? c.type : "other"] += amt;
  });
  const totalBatch = materialTotal + sums.packaging + sums.labor + sums.overhead + sums.other;
  const sp = Math.max(n(selling_price), 0);
  const hpp = y > 0 ? totalBatch / y : null;
  const profit = hpp !== null && sp > 0 ? sp - hpp : null;
  const tm = target_margin !== null && target_margin !== undefined && target_margin !== "" ? target_margin : defaultMargin;
  return {
    ...suggestPrice(hpp, tm), target_margin_is_override: target_margin !== null && target_margin !== undefined && target_margin !== "",
    items: rows, item_count: rows.length, material_total: materialTotal, packaging_total: sums.packaging, labor_total: sums.labor, overhead_total: sums.overhead, other_total: sums.other,
    total_batch: totalBatch, yield_qty: y, hpp_per_unit: hpp, selling_price: sp, profit_per_unit: profit,
    margin_pct: profit !== null && sp > 0 ? (profit / sp) * 100 : null, markup_pct: profit !== null && hpp > 0 ? (profit / hpp) * 100 : null,
    warning: y > 0 ? null : "Hasil produksi (yield) = 0, HPP per unit tidak dapat dihitung", errors: rows.filter((r) => r.error).map((r) => `Baris ${r.no}: ${r.error}`),
  };
}
