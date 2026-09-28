import { useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Copy } from "lucide-react";
import { api, errMsg } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatRp, formatNum, formatPct } from "../lib/format";
import { PageHeader, DataTable, ConfirmDialog } from "../components/common";
import RecipeEditor from "../components/RecipeEditor";
import { Button } from "../components/ui/button";

export function useRecipeDeps() {
  const products = useApi("/products");
  const materials = useApi("/materials");
  const units = useApi("/units");
  const conversions = useApi("/unit-conversions");
  const recipes = useApi("/recipes");
  const meta = useApi("/meta");
  return { products: products.data || [], materials: materials.data || [], units: units.data || [], conversions: conversions.data || [], recipes: recipes.data || [], meta: meta.data, reloadRecipes: recipes.reload, loading: recipes.loading };
}

export default function Recipes() {
  const deps = useRecipeDeps();
  const [editing, setEditing] = useState(null);
  const [del, setDel] = useState(null);
  const openEdit = async (r, duplicate = false) => {
    try {
      const { data } = await api.get(`/recipes/${r.id}`);
      setEditing(duplicate ? { ...data, id: undefined, name: `${data.name} (copy)`, is_default: false, items: data.items.map(({ id, ...i }) => i) } : data);
    } catch (e) { toast.error(errMsg(e)); }
  };
  const remove = async () => { try { await api.delete(`/recipes/${del.id}`); toast.success("Resep dihapus"); setDel(null); deps.reloadRecipes(); } catch (e) { toast.error(errMsg(e)); } };
  if (editing) {
    return (
      <div data-testid="recipes-page">
        <PageHeader title={editing.id ? `Edit Resep: ${editing.name}` : "Resep Baru"} subtitle="Semua bahan dihitung otomatis secara realtime. Jumlah bahan tidak terbatas." />
        <RecipeEditor key={editing.id || "new"} initial={editing} {...deps} onSaved={() => { setEditing(null); deps.reloadRecipes(); }} onCancel={() => setEditing(null)} />
      </div>
    );
  }
  return (
    <div data-testid="recipes-page">
      <PageHeader title="Resep / BOM" subtitle="Bill of Materials per produk — mendukung banyak versi resep & sub-resep" actions={<Button onClick={() => setEditing({})} data-testid="recipe-add-btn"><Plus className="mr-1 h-4 w-4" />Resep Baru</Button>} />
      <DataTable testId="recipes-table" filename="resep" rows={deps.recipes} loading={deps.loading} searchKeys={["name"]} columns={[
        { key: "name", label: "Nama Resep", render: (r) => <div><p className="font-medium">{r.name}</p><p className="text-xs text-muted-foreground">{r.version}{r.is_default && " · utama"}{!r.product_id && " · sub-resep"}</p></div> },
        { label: "Produk", key: (r) => r.product?.name || "—" }, { label: "Jml Bahan", align: "right", key: (r) => r.summary?.item_count ?? "-" },
        { label: "Yield", align: "right", key: (r) => `${formatNum(r.yield_qty)} ${r.yield_unit || ""}` }, { label: "Total Bahan", align: "right", key: (r) => (r.summary?.error ? "-" : formatRp(r.summary?.material_total, true)) },
        { label: "HPP Batch", align: "right", key: (r) => (r.summary?.error ? "-" : formatRp(r.summary?.total_batch, true)) },
        { label: "HPP / Unit", align: "right", render: (r) => (r.summary?.error ? <span className="text-xs text-red-600">{r.summary.error}</span> : <b className="num">{formatRp(r.summary?.hpp_per_unit, true)}</b>) },
        { label: "Harga Jual", align: "right", key: (r) => formatRp(r.selling_price) }, { label: "Margin", align: "right", key: (r) => (r.summary?.margin_pct == null ? "-" : formatPct(r.summary.margin_pct)) },
        { label: "Harga Saran", align: "right", render: (r) => (r.summary?.suggested_price_rounded == null ? "-" : <span className={`num ${r.selling_price > 0 && r.selling_price < r.summary.suggested_price ? "text-orange-600" : "text-teal-700"}`} title={`Target ${formatPct(r.summary.target_margin_pct)} · tepat ${formatRp(r.summary.suggested_price, true)}`} data-testid="recipe-suggested-price">{formatRp(r.summary.suggested_price_rounded)}<span className="ml-1 text-[10px] text-muted-foreground">@{formatPct(r.summary.target_margin_pct)}</span></span>) },
        { label: "Aksi", noExport: true, align: "right", render: (r) => (
          <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => openEdit(r)} data-testid="recipe-edit-btn"><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" onClick={() => openEdit(r, true)} title="Duplikat" data-testid="recipe-duplicate-btn"><Copy className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="recipe-delete-btn"><Trash2 className="h-4 w-4" /></Button></div>) },
      ]} />
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Hapus resep ${del?.name}?`} description="Produksi yang sudah tercatat tetap menyimpan snapshot resep & HPP-nya." />
    </div>
  );
}
