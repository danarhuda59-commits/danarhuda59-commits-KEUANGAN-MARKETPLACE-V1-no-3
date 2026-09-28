import { useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { api, errMsg } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatRp, formatNum, formatPct, formatDateTime } from "../lib/format";
import { PageHeader, Field, SelectInput, DataTable } from "../components/common";
import RecipeEditor from "../components/RecipeEditor";
import { useRecipeDeps } from "./Recipes";
import { Button } from "../components/ui/button";

export default function HppCalculator() {
  const deps = useRecipeDeps();
  const calcs = useApi("/hpp/calculations");
  const [productId, setProductId] = useState("");
  const [recipeId, setRecipeId] = useState("");
  const [initial, setInitial] = useState({});
  const [key, setKey] = useState(0);
  const productRecipes = deps.recipes.filter((r) => r.product_id === productId);
  const loadRecipe = async (rid) => {
    setRecipeId(rid);
    if (!rid) { setInitial({ product_id: productId }); setKey((k) => k + 1); return; }
    try { const { data } = await api.get(`/recipes/${rid}`); setInitial(data); setKey((k) => k + 1); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="hpp-page">
      <PageHeader title="Perhitungan HPP" subtitle="Pilih produk & resep, ubah bahan/qty/waste/yield — semua total dihitung realtime" />
      <div className="card-panel mb-6 grid gap-4 sm:grid-cols-2">
        <Field label="Pilih Produk"><SelectInput value={productId} onChange={(v) => { setProductId(v); setRecipeId(""); setInitial({ product_id: v, selling_price: deps.products.find((p) => p.id === v)?.selling_price || 0, yield_unit: deps.products.find((p) => p.id === v)?.unit }); setKey((k) => k + 1); }} options={deps.products.map((p) => ({ value: p.id, label: `${p.name} (${p.sku})` }))} data-testid="hpp-product-select" /></Field>
        <Field label="Pilih Resep" hint={productId && productRecipes.length === 0 ? "Produk ini belum punya resep — susun bahan di bawah lalu simpan sebagai resep." : ""}><SelectInput value={recipeId} onChange={loadRecipe} options={productRecipes.map((r) => ({ value: r.id, label: `${r.name} — HPP ${formatRp(r.summary?.hpp_per_unit, true)}` }))} placeholder="— Resep baru / kosong —" data-testid="hpp-recipe-select" /></Field>
      </div>
      <RecipeEditor key={key} initial={initial} {...deps} mode="calculator" onSaved={() => { calcs.reload(); deps.reloadRecipes(); }} />
      <div className="mt-8">
        <h3 className="mb-3 font-heading font-semibold">Perhitungan Tersimpan</h3>
        <DataTable testId="calculations-table" filename="perhitungan-hpp" rows={calcs.data || []} pageSize={5} columns={[
          { key: "name", label: "Nama" }, { label: "Tanggal", key: (r) => formatDateTime(r.created_at) }, { label: "Bahan", align: "right", key: (r) => r.result?.item_count }, { label: "Total Bahan", align: "right", key: (r) => formatRp(r.result?.material_total, true) },
          { label: "HPP Batch", align: "right", key: (r) => formatRp(r.result?.total_batch, true) }, { label: "Yield", align: "right", key: (r) => formatNum(r.result?.yield_qty) }, { label: "HPP/Unit", align: "right", key: (r) => formatRp(r.result?.hpp_per_unit, true) },
          { label: "Margin", align: "right", key: (r) => (r.result?.margin_pct == null ? "-" : formatPct(r.result.margin_pct)) },
          { label: "", noExport: true, align: "right", render: (r) => <Button variant="ghost" size="sm" className="text-red-600" onClick={async () => { await api.delete(`/hpp/calculations/${r.id}`); calcs.reload(); }} data-testid="calc-delete-btn"><Trash2 className="h-4 w-4" /></Button> },
        ]} />
      </div>
    </div>
  );
}
