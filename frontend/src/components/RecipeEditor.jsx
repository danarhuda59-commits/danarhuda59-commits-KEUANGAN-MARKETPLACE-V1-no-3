import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, ArrowUp, ArrowDown, Save, AlertTriangle, Target } from "lucide-react";
import { api, errMsg } from "../lib/api";
import { computeHpp } from "../lib/hpp";
import { useAuth } from "../lib/auth";
import { formatRp, formatNum, formatPct } from "../lib/format";
import { Field, TextInput, NumberInput, SelectInput, TextArea, SummaryRow } from "./common";
import { Button } from "./ui/button";

export const emptyRecipe = { product_id: "", name: "", version: "v1", yield_qty: 1, yield_unit: "pcs", selling_price: 0, target_margin: null, is_default: true, is_sub_recipe: false, notes: "", items: [], extra_costs: [] };
const newItem = () => ({ _k: Math.random().toString(36).slice(2), material_id: "", sub_recipe_id: null, qty: "", unit: "", waste_pct: 0 });

export function useRecipeCalc(recipe, materials, conversions, recipes, defaultMargin = null) {
  const matMap = useMemo(() => Object.fromEntries((materials || []).map((m) => [m.id, m])), [materials]);
  const convMap = useMemo(() => Object.fromEntries((conversions || []).map((c) => [`${c.from_unit}>${c.to_unit}`, parseFloat(c.factor)])), [conversions]);
  const subCosts = useMemo(() => Object.fromEntries((recipes || []).map((r) => [r.id, { hpp_per_unit: r.summary?.hpp_per_unit || 0, name: r.name, yield_unit: r.yield_unit }])), [recipes]);
  const result = useMemo(() => computeHpp(recipe, matMap, convMap, subCosts, defaultMargin), [recipe, matMap, convMap, subCosts, defaultMargin]);
  return { result, matMap };
}

export function HppSummary({ r, testId = "hpp-summary", onApplyPrice }) {
  const tone = r.profit_per_unit === null ? "default" : r.profit_per_unit >= 0 ? "good" : "bad";
  const hasSuggestion = r.suggested_price !== null && r.suggested_price !== undefined;
  const belowTarget = hasSuggestion && r.selling_price > 0 && r.selling_price < r.suggested_price - 0.005;
  return (
    <div className="card-panel space-y-0.5" data-testid={testId}>
      <h3 className="mb-3 font-heading font-semibold">Ringkasan HPP</h3>
      <SummaryRow label={`Total Bahan (${r.item_count} item)`} value={formatRp(r.material_total, true)} testId="sum-material" />
      <SummaryRow label="Kemasan" value={formatRp(r.packaging_total, true)} testId="sum-packaging" />
      <SummaryRow label="Tenaga Kerja" value={formatRp(r.labor_total, true)} testId="sum-labor" />
      <SummaryRow label="Overhead" value={formatRp(r.overhead_total, true)} testId="sum-overhead" />
      <SummaryRow label="Biaya Lainnya" value={formatRp(r.other_total, true)} testId="sum-other" />
      <SummaryRow label="TOTAL HPP BATCH" value={formatRp(r.total_batch, true)} bold testId="sum-total-batch" />
      <SummaryRow label="Hasil Produksi" value={`${formatNum(r.yield_qty)} unit`} testId="sum-yield" />
      <SummaryRow label="HPP PER UNIT" value={r.hpp_per_unit === null ? "—" : formatRp(r.hpp_per_unit, true)} bold tone="primary" testId="sum-hpp-unit" />
      <SummaryRow label="Harga Jual" value={formatRp(r.selling_price)} testId="sum-selling" />
      <SummaryRow label="Laba per Unit" value={r.profit_per_unit === null ? "—" : formatRp(r.profit_per_unit, true)} tone={tone} testId="sum-profit" />
      <SummaryRow label="Margin" value={r.margin_pct === null ? "—" : formatPct(r.margin_pct)} tone={tone} testId="sum-margin" />
      <SummaryRow label="Markup" value={r.markup_pct === null ? "—" : formatPct(r.markup_pct)} tone={tone} testId="sum-markup" />
      {r.target_margin_pct !== null && r.target_margin_pct !== undefined && (
        <div className="mt-3 rounded-md border border-teal-200 bg-teal-50/60 p-3 dark:border-teal-800 dark:bg-teal-900/20" data-testid="target-margin-box">
          <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-teal-800 dark:text-teal-200"><Target className="h-3.5 w-3.5" />Target Margin {formatPct(r.target_margin_pct)}{r.target_margin_is_override ? " (override resep)" : " (default usaha)"}</div>
          {hasSuggestion ? (
            <>
              <SummaryRow label="Harga Saran (tepat)" value={formatRp(r.suggested_price, true)} testId="sum-suggested-price" />
              <SummaryRow label="Harga Saran (bulat ke atas Rp100)" value={formatRp(r.suggested_price_rounded)} bold tone="primary" testId="sum-suggested-price-rounded" />
              <SummaryRow label="Laba/unit di harga saran" value={formatRp(r.suggested_profit_per_unit, true)} testId="sum-suggested-profit" />
              <p className="mt-1 text-[11px] text-muted-foreground" data-testid="suggestion-note">Rumus: harga = HPP/unit ÷ (1 − target margin). Margin dihitung dari harga jual, bukan markup dari HPP.</p>
              {belowTarget && <p className="mt-1 text-[11px] text-orange-700 dark:text-orange-300" data-testid="below-target-warning">Harga jual saat ini di bawah harga saran — margin belum mencapai target.</p>}
              {onApplyPrice && <Button size="sm" variant="outline" className="mt-2 w-full" onClick={() => onApplyPrice(r.suggested_price_rounded)} data-testid="apply-suggested-price-btn">Pakai harga saran {formatRp(r.suggested_price_rounded)}</Button>}
              <PriceSimulation rows={r.price_simulation} sellingPrice={r.selling_price} onApplyPrice={onApplyPrice} />
            </>
          ) : <p className="text-xs text-muted-foreground" data-testid="suggestion-note">{r.suggestion_note || "HPP belum bisa dihitung, harga saran belum tersedia."}</p>}
        </div>
      )}
      {r.warning && <p className="mt-2 flex items-center gap-2 rounded-md bg-orange-50 p-2 text-xs text-orange-700 dark:bg-orange-900/30 dark:text-orange-300" data-testid="hpp-warning"><AlertTriangle className="h-3.5 w-3.5" />{r.warning}</p>}
      {r.errors?.map((e, i) => <p key={i} className="rounded-md bg-red-50 p-2 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-300" data-testid="hpp-error">{e}</p>)}
    </div>
  );
}

export function PriceSimulation({ rows, sellingPrice, onApplyPrice }) {
  if (!rows?.length) return null;
  return (
    <div className="mt-3 border-t border-teal-200 pt-2 dark:border-teal-800" data-testid="price-simulation">
      <p className="mb-1 text-xs font-semibold text-teal-800 dark:text-teal-200">Simulasi Harga per Margin</p>
      <table className="w-full text-xs">
        <thead><tr className="text-muted-foreground"><th className="py-1 text-left font-medium">Margin</th><th className="py-1 text-right font-medium">Harga (bulat)</th><th className="py-1 text-right font-medium">Laba/unit</th>{onApplyPrice && <th />}</tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.margin_pct} className={s.is_target ? "font-semibold text-teal-800 dark:text-teal-200" : ""} data-testid={`sim-row-${s.margin_pct}`}>
              <td className="py-1">{formatPct(s.margin_pct)}{s.is_target && <span className="ml-1 text-[10px] font-normal text-muted-foreground">target</span>}</td>
              <td className="num py-1 text-right" title={`Tepat ${formatRp(s.price, true)}`}>{formatRp(s.price_rounded)}{sellingPrice > 0 && Math.abs(sellingPrice - s.price_rounded) < 0.5 && <span className="ml-1 text-[10px] text-muted-foreground">saat ini</span>}</td>
              <td className="num py-1 text-right">{formatRp(s.profit_per_unit, true)}</td>
              {onApplyPrice && <td className="py-1 text-right"><button type="button" className="text-teal-700 underline-offset-2 hover:underline dark:text-teal-300" onClick={() => onApplyPrice(s.price_rounded)} data-testid={`sim-apply-${s.margin_pct}`}>pakai</button></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RecipeEditor({ initial, products, materials, units, conversions, recipes, meta, mode = "recipe", onSaved, onCancel }) {
  const { business } = useAuth();
  const defaultMargin = business?.target_margin ?? 30;
  const [r, setR] = useState(() => ({ ...emptyRecipe, ...initial, target_margin: initial?.target_margin ?? null, items: (initial?.items || []).map((i) => ({ ...i, _k: i.id || Math.random().toString(36).slice(2) })), extra_costs: initial?.extra_costs || [] }));
  const [useNested, setUseNested] = useState(() => (initial?.items || []).some((i) => i.sub_recipe_id));
  const [saving, setSaving] = useState(false);
  const [calcName, setCalcName] = useState("");
  const { result, matMap } = useRecipeCalc(r, materials, conversions, recipes, defaultMargin);
  const set = (k, v) => setR((s) => ({ ...s, [k]: v }));
  const setItem = (idx, patch) => setR((s) => ({ ...s, items: s.items.map((it, i) => (i === idx ? { ...it, ...patch } : it)) }));
  const move = (idx, dir) => setR((s) => { const items = [...s.items]; const j = idx + dir; if (j < 0 || j >= items.length) return s; [items[idx], items[j]] = [items[j], items[idx]]; return { ...s, items }; });
  const removeItem = (idx) => setR((s) => ({ ...s, items: s.items.filter((_, i) => i !== idx) }));
  const setExtra = (idx, patch) => setR((s) => ({ ...s, extra_costs: s.extra_costs.map((c, i) => (i === idx ? { ...c, ...patch } : c)) }));
  const subOptions = (recipes || []).filter((x) => x.id !== initial?.id).map((x) => ({ value: x.id, label: `${x.name} (${formatRp(x.summary?.hpp_per_unit, true)}/${x.yield_unit || "unit"})` }));
  const unitOpts = (units || []).map((u) => ({ value: u.code, label: u.code }));

  const marginOverride = r.target_margin === null || r.target_margin === undefined || r.target_margin === "" ? null : parseFloat(r.target_margin);
  const payload = () => ({ ...r, product_id: r.product_id || null, yield_qty: parseFloat(r.yield_qty || 0), selling_price: parseFloat(r.selling_price || 0), target_margin: Number.isFinite(marginOverride) ? marginOverride : null,
    items: r.items.map(({ _k, id, ...it }) => ({ material_id: it.sub_recipe_id ? null : it.material_id || null, sub_recipe_id: it.sub_recipe_id || null, qty: parseFloat(it.qty || 0), unit: it.unit || null, waste_pct: parseFloat(it.waste_pct || 0) })),
    extra_costs: r.extra_costs.map((c) => ({ ...c, value: parseFloat(c.value || 0) })) });

  const validate = () => {
    if (!r.name.trim()) return "Nama resep wajib diisi";
    if (r.items.length === 0) return "Tambahkan minimal satu bahan";
    if (result.errors.length) return result.errors[0];
    if (r.items.some((it) => !(parseFloat(it.qty) > 0))) return "Qty setiap bahan harus lebih dari 0";
    if (marginOverride !== null && !(marginOverride >= 0 && marginOverride < 100)) return "Target margin harus antara 0 dan 99,99%";
    return null;
  };
  const save = async () => {
    const err = validate(); if (err) return toast.error(err);
    setSaving(true);
    try {
      const body = payload();
      const res = initial?.id ? await api.put(`/recipes/${initial.id}`, body) : await api.post("/recipes", body);
      toast.success("Resep tersimpan");
      onSaved?.(res.data);
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  const saveCalc = async () => {
    if (r.items.length === 0) return toast.error("Tambahkan minimal satu bahan");
    if (result.errors.length) return toast.error(result.errors[0]);
    setSaving(true);
    try {
      const b = payload();
      await api.post("/hpp/calculations", { name: calcName || r.name || "Perhitungan HPP", product_id: b.product_id, recipe_id: initial?.id || null, items: b.items, extra_costs: b.extra_costs, yield_qty: b.yield_qty, selling_price: b.selling_price, target_margin: b.target_margin });
      toast.success("Perhitungan HPP tersimpan");
      onSaved?.();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_340px]" data-testid="recipe-editor">
      <div className="min-w-0 space-y-6">
        <div className="card-panel grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Produk" className="sm:col-span-2"><SelectInput value={r.product_id} onChange={(v) => { const p = (products || []).find((x) => x.id === v); setR((s) => ({ ...s, product_id: v, selling_price: p && !parseFloat(s.selling_price) ? p.selling_price : s.selling_price, yield_unit: p?.unit || s.yield_unit })); }} options={(products || []).map((p) => ({ value: p.id, label: `${p.name} (${p.sku})` }))} placeholder="— Tanpa produk (sub-resep) —" data-testid="recipe-product-select" /></Field>
          <Field label="Nama Resep" required className="sm:col-span-2"><TextInput value={r.name} onChange={(e) => set("name", e.target.value)} placeholder="cth: Baso Aci Original v1" data-testid="recipe-name-input" /></Field>
          <Field label={mode === "calculator" ? "Jumlah Produksi / Yield" : "Hasil Produksi (Yield)"} required><NumberInput value={r.yield_qty} onChange={(v) => set("yield_qty", v)} data-testid="recipe-yield-input" /></Field>
          <Field label="Satuan Yield"><SelectInput value={r.yield_unit} onChange={(v) => set("yield_unit", v)} options={unitOpts} data-testid="recipe-yield-unit-select" /></Field>
          <Field label="Harga Jual / unit"><NumberInput value={r.selling_price} onChange={(v) => set("selling_price", v)} data-testid="recipe-selling-price-input" /></Field>
          <Field label="Target Margin % (opsional)" hint={`Kosong = pakai default usaha ${formatPct(defaultMargin)}`}><NumberInput value={r.target_margin ?? ""} onChange={(v) => set("target_margin", v === "" || v === null ? null : v)} placeholder={String(defaultMargin)} data-testid="recipe-target-margin-input" /></Field>
          <Field label="Versi"><TextInput value={r.version || ""} onChange={(e) => set("version", e.target.value)} data-testid="recipe-version-input" /></Field>
          <div className="flex flex-wrap items-center gap-4 sm:col-span-2 lg:col-span-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={r.is_default} onChange={(e) => set("is_default", e.target.checked)} className="h-4 w-4 accent-teal-700" data-testid="recipe-default-checkbox" />Resep utama untuk produk ini</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={useNested} onChange={(e) => setUseNested(e.target.checked)} className="h-4 w-4 accent-teal-700" data-testid="recipe-nested-checkbox" />Gunakan sub-resep (nested, opsional)</label>
          </div>
        </div>

        <div className="card-panel">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-heading font-semibold">Bahan ({r.items.length})</h3>
            <Button size="sm" onClick={() => setR((s) => ({ ...s, items: [...s.items, newItem()] }))} data-testid="recipe-add-item-btn"><Plus className="mr-1 h-4 w-4" />TAMBAH BAHAN</Button>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>No</th><th className="min-w-[200px]">Bahan</th><th className="w-24">Qty</th><th className="w-32">Satuan</th><th className="text-right">Harga Dasar</th><th className="text-right">Konversi</th><th className="w-20">Waste %</th><th className="text-right">Biaya</th><th></th></tr></thead>
              <tbody>
                {r.items.length === 0 && <tr><td colSpan={9} className="py-8 text-center text-sm text-muted-foreground">Belum ada bahan. Klik "TAMBAH BAHAN".</td></tr>}
                {r.items.map((it, idx) => {
                  const row = result.items[idx] || {};
                  const m = matMap[it.material_id];
                  const itemUnits = m ? [...new Set([m.usage_unit, m.purchase_unit, ...unitOpts.map((u) => u.value)])].map((u) => ({ value: u, label: u })) : unitOpts;
                  return (
                    <tr key={it._k} data-testid="recipe-item-row">
                      <td className="num text-muted-foreground">{idx + 1}</td>
                      <td>
                        {useNested && (
                          <label className="mb-1 flex items-center gap-1 text-[11px] text-muted-foreground"><input type="checkbox" checked={!!it.sub_recipe_id || it._sub} onChange={(e) => setItem(idx, e.target.checked ? { _sub: true, material_id: "", sub_recipe_id: it.sub_recipe_id || "" } : { _sub: false, sub_recipe_id: null })} className="h-3 w-3" data-testid="item-sub-toggle" />Sub-resep</label>
                        )}
                        {(it.sub_recipe_id || it._sub) && useNested
                          ? <SelectInput value={it.sub_recipe_id || ""} onChange={(v) => setItem(idx, { sub_recipe_id: v, material_id: "", unit: (recipes || []).find((x) => x.id === v)?.yield_unit || "" })} options={subOptions} placeholder="Pilih sub-resep" data-testid="item-subrecipe-select" />
                          : <SelectInput value={it.material_id} onChange={(v) => { const mm = matMap[v]; setItem(idx, { material_id: v, sub_recipe_id: null, unit: mm?.usage_unit || "" }); }} options={(materials || []).map((x) => ({ value: x.id, label: `${x.name} (${formatRp(x.last_price)}/${x.purchase_unit})` }))} placeholder="Pilih bahan" data-testid="item-material-select" />}
                        {row.error && <p className="mt-1 text-[11px] text-red-600">{row.error}</p>}
                      </td>
                      <td><NumberInput value={it.qty} onChange={(v) => setItem(idx, { qty: v })} className="h-9" data-testid="item-qty-input" /></td>
                      <td><SelectInput value={it.unit} onChange={(v) => setItem(idx, { unit: v })} options={itemUnits} allowEmpty={false} className="h-9" data-testid="item-unit-select" /></td>
                      <td className="text-right num text-xs">{m ? `${formatRp(m.last_price)}/${m.purchase_unit}` : it.sub_recipe_id ? `${formatRp(row.unit_price, true)}/${row.unit}` : "-"}</td>
                      <td className="text-right num text-xs">{m ? <>1 {m.purchase_unit} = {formatNum(m.conversion_factor, 4)} {m.usage_unit}<br /><span className="text-muted-foreground">{formatRp(row.unit_price, true)}/{m.usage_unit}</span></> : "-"}</td>
                      <td><NumberInput value={it.waste_pct} onChange={(v) => setItem(idx, { waste_pct: v })} className="h-9" data-testid="item-waste-input" /></td>
                      <td className="text-right num font-medium" data-testid="item-cost">{formatRp(row.cost, true)}</td>
                      <td>
                        <div className="flex justify-end">
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => move(idx, -1)} disabled={idx === 0} data-testid="item-up-btn"><ArrowUp className="h-3.5 w-3.5" /></Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => move(idx, 1)} disabled={idx === r.items.length - 1} data-testid="item-down-btn"><ArrowDown className="h-3.5 w-3.5" /></Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-red-600" onClick={() => removeItem(idx)} data-testid="item-delete-btn"><Trash2 className="h-3.5 w-3.5" /></Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              {r.items.length > 0 && <tfoot><tr className="border-t bg-muted/40 font-semibold"><td colSpan={7} className="text-right px-3 py-2">TOTAL BAHAN</td><td className="text-right num px-3 py-2" data-testid="items-total">{formatRp(result.material_total, true)}</td><td /></tr></tfoot>}
            </table>
          </div>
        </div>

        <div className="card-panel">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-heading font-semibold">Kemasan, Tenaga Kerja, Overhead & Biaya Lainnya</h3>
            <Button size="sm" variant="outline" onClick={() => setR((s) => ({ ...s, extra_costs: [...s.extra_costs, { name: "", type: "overhead", method: "per_batch", value: "" }] }))} data-testid="recipe-add-cost-btn"><Plus className="mr-1 h-4 w-4" />Tambah Biaya</Button>
          </div>
          {r.extra_costs.length === 0 && <p className="text-sm text-muted-foreground">Belum ada biaya tambahan (kemasan, listrik, gas, tenaga kerja, sewa, penyusutan, dll).</p>}
          <div className="space-y-2">
            {r.extra_costs.map((c, idx) => (
              <div key={idx} className="grid gap-2 sm:grid-cols-[1fr_160px_170px_140px_auto] items-center" data-testid="extra-cost-row">
                <TextInput placeholder="Nama biaya (cth: Gas, Listrik)" value={c.name} onChange={(e) => setExtra(idx, { name: e.target.value })} className="h-9" data-testid="cost-name-input" />
                <SelectInput value={c.type} onChange={(v) => setExtra(idx, { type: v })} options={meta?.extra_cost_types || []} allowEmpty={false} className="h-9" data-testid="cost-type-select" />
                <SelectInput value={c.method} onChange={(v) => setExtra(idx, { method: v })} options={meta?.cost_methods || []} allowEmpty={false} className="h-9" data-testid="cost-method-select" />
                <NumberInput value={c.value} onChange={(v) => setExtra(idx, { value: v })} placeholder={c.method === "pct_material" ? "%" : "Rp"} className="h-9" data-testid="cost-value-input" />
                <Button variant="ghost" size="icon" className="h-8 w-8 text-red-600" onClick={() => setR((s) => ({ ...s, extra_costs: s.extra_costs.filter((_, i) => i !== idx) }))} data-testid="cost-delete-btn"><Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            ))}
          </div>
        </div>
        <Field label="Catatan"><TextArea value={r.notes || ""} onChange={(e) => set("notes", e.target.value)} data-testid="recipe-notes-input" /></Field>
      </div>

      <div className="min-w-0 space-y-4 xl:sticky xl:top-20 self-start">
        <HppSummary r={result} onApplyPrice={(p) => { set("selling_price", p); toast.success(`Harga jual diisi ${formatRp(p)}`); }} />
        <div className="card-panel space-y-2">
          {mode === "calculator" && <Field label="Nama perhitungan"><TextInput value={calcName} onChange={(e) => setCalcName(e.target.value)} placeholder={r.name || "Perhitungan HPP"} data-testid="calc-name-input" /></Field>}
          {mode === "calculator" && <Button className="w-full" onClick={saveCalc} disabled={saving} data-testid="save-calculation-btn"><Save className="mr-1 h-4 w-4" />Simpan Perhitungan</Button>}
          <Button className="w-full" variant={mode === "calculator" ? "outline" : "default"} onClick={save} disabled={saving} data-testid="recipe-save-btn"><Save className="mr-1 h-4 w-4" />{initial?.id ? "Simpan ke Resep" : "Simpan sebagai Resep Baru"}</Button>
          {onCancel && <Button className="w-full" variant="ghost" onClick={onCancel} data-testid="recipe-cancel-btn">Batal</Button>}
        </div>
      </div>
    </div>
  );
}
