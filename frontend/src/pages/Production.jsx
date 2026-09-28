import { useState } from "react";
import { toast } from "sonner";
import { Plus, Eye, Trash2 } from "lucide-react";
import { api, errMsg } from "../lib/api";
import { useApi, qs } from "../lib/hooks";
import { formatRp, formatNum, formatDate, todayISO } from "../lib/format";
import { PageHeader, DataTable, Modal, ConfirmDialog, Field, TextInput, NumberInput, SelectInput, TextArea, SummaryRow, PeriodFilter, usePeriod } from "../components/common";
import { Button } from "../components/ui/button";

function ProductionDetail({ id, onClose }) {
  const { data: d } = useApi(`/production/${id}`);
  if (!d) return null;
  return (
    <Modal open onClose={onClose} title={`${d.number} — ${d.product_name}`} description={`${formatDate(d.date)} · Resep: ${d.recipe_name} · ${d.batch_count} batch · Operator: ${d.operator || "-"}`} wide>
      <div className="table-wrap"><table>
        <thead><tr><th>No</th><th>Bahan</th><th className="text-right">Qty</th><th>Satuan</th><th className="text-right">Harga/Satuan (snapshot)</th><th className="text-right">Waste</th><th className="text-right">Biaya</th></tr></thead>
        <tbody>{(d.items || []).map((it) => <tr key={it.id}><td>{it.no}</td><td>{it.material_name}</td><td className="text-right num">{formatNum(it.quantity, 3)}</td><td>{it.unit}</td><td className="text-right num">{formatRp(it.unit_price, true)}</td><td className="text-right num">{formatNum(it.waste_pct)}%</td><td className="text-right num">{formatRp(it.cost, true)}</td></tr>)}</tbody>
      </table></div>
      <div className="grid gap-x-8 sm:grid-cols-2">
        <div><SummaryRow label="Total Bahan" value={formatRp(d.material_total, true)} /><SummaryRow label="Kemasan" value={formatRp(d.packaging_total, true)} /><SummaryRow label="Tenaga Kerja" value={formatRp(d.labor_total, true)} /><SummaryRow label="Overhead" value={formatRp(d.overhead_total, true)} /><SummaryRow label="Biaya Lainnya" value={formatRp(d.other_total, true)} /></div>
        <div><SummaryRow label="TOTAL BIAYA PRODUKSI" value={formatRp(d.total_cost, true)} bold /><SummaryRow label="Hasil Produksi" value={`${formatNum(d.qty_produced)} ${d.unit || ""}`} /><SummaryRow label="HPP PER UNIT (snapshot)" value={formatRp(d.hpp_per_unit, true)} bold tone="primary" /><SummaryRow label="Harga Jual saat itu" value={formatRp(d.selling_price)} /></div>
      </div>
      {d.notes && <p className="text-sm text-muted-foreground">Catatan: {d.notes}</p>}
    </Modal>
  );
}

export default function Production() {
  const period = usePeriod("all");
  const { data, loading, reload } = useApi(`/production${qs(period.range)}`, [period.range.start, period.range.end]);
  const { data: products } = useApi("/products");
  const { data: recipes } = useApi("/recipes");
  const [form, setForm] = useState(null);
  const [detail, setDetail] = useState(null);
  const [del, setDel] = useState(null);
  const [saving, setSaving] = useState(false);
  const recs = (recipes || []).filter((r) => r.product_id === form?.product_id);
  const selRecipe = recs.find((r) => r.id === form?.recipe_id);
  const estCost = selRecipe?.summary?.total_batch != null ? selRecipe.summary.total_batch * parseFloat(form.batch_count || 0) : null;
  const save = async () => {
    if (!form.product_id || !form.recipe_id) return toast.error("Pilih produk dan resep");
    if (!(parseFloat(form.qty_produced) > 0)) return toast.error("Qty produksi harus lebih dari 0");
    setSaving(true);
    try {
      await api.post("/production", { ...form, batch_count: parseFloat(form.batch_count || 1), qty_produced: parseFloat(form.qty_produced) });
      toast.success("Produksi tercatat: stok bahan berkurang, stok produk bertambah");
      setForm(null); reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  const remove = async () => { try { await api.delete(`/production/${del.id}`); toast.success("Produksi dibatalkan & stok dikembalikan"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="production-page">
      <PageHeader title="Produksi" subtitle="Setiap produksi memotong stok bahan, menambah stok produk & menyimpan snapshot HPP" actions={<><PeriodFilter period={period} /><Button onClick={() => setForm({ product_id: "", recipe_id: "", date: todayISO(), batch_count: 1, qty_produced: "", operator: "", notes: "" })} data-testid="production-add-btn"><Plus className="mr-1 h-4 w-4" />Produksi Baru</Button></>} />
      <DataTable testId="production-table" filename="produksi" rows={data || []} loading={loading} columns={[
        { key: "number", label: "Nomor" }, { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "product_name", label: "Produk" }, { key: "recipe_name", label: "Resep" },
        { key: "batch_count", label: "Batch", align: "right" }, { key: "qty_produced", label: "Qty", align: "right", render: (r) => `${formatNum(r.qty_produced)} ${r.unit || ""}` },
        { key: "total_cost", label: "Total Biaya", align: "right", render: (r) => formatRp(r.total_cost) }, { key: "hpp_per_unit", label: "HPP/Unit", align: "right", render: (r) => <b>{formatRp(r.hpp_per_unit, true)}</b> }, { key: "operator", label: "Operator" },
        { label: "Aksi", noExport: true, align: "right", render: (r) => <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => setDetail(r.id)} data-testid="production-detail-btn"><Eye className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="production-delete-btn"><Trash2 className="h-4 w-4" /></Button></div> },
      ]} />
      <Modal open={!!form} onClose={() => setForm(null)} title="Catat Produksi" footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} disabled={saving} data-testid="production-save-btn">Simpan Produksi</Button></>}>
        {form && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tanggal"><TextInput type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="production-date-input" /></Field>
          <Field label="Produk" required><SelectInput value={form.product_id} onChange={(v) => setForm({ ...form, product_id: v, recipe_id: "" })} options={(products || []).map((p) => ({ value: p.id, label: p.name }))} data-testid="production-product-select" /></Field>
          <Field label="Resep" required className="sm:col-span-2"><SelectInput value={form.recipe_id} onChange={(v) => { const r = recs.find((x) => x.id === v); setForm({ ...form, recipe_id: v, qty_produced: r ? r.yield_qty * parseFloat(form.batch_count || 1) : form.qty_produced }); }} options={recs.map((r) => ({ value: r.id, label: `${r.name} (yield ${formatNum(r.yield_qty)} ${r.yield_unit || ""}, HPP ${formatRp(r.summary?.hpp_per_unit, true)})` }))} data-testid="production-recipe-select" /></Field>
          <Field label="Jumlah Batch" hint="Bahan dikalikan jumlah batch"><NumberInput value={form.batch_count} onChange={(v) => setForm({ ...form, batch_count: v, qty_produced: selRecipe ? selRecipe.yield_qty * parseFloat(v || 0) : form.qty_produced })} data-testid="production-batch-input" /></Field>
          <Field label="Qty Hasil Produksi (aktual)" required><NumberInput value={form.qty_produced} onChange={(v) => setForm({ ...form, qty_produced: v })} data-testid="production-qty-input" /></Field>
          <Field label="Operator"><TextInput value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })} data-testid="production-operator-input" /></Field>
          <Field label="Catatan"><TextInput value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} data-testid="production-notes-input" /></Field>
          {selRecipe && <div className="sm:col-span-2 rounded-lg bg-muted/50 p-3 text-sm"><SummaryRow label="Estimasi total biaya (harga bahan saat ini)" value={formatRp(estCost, true)} /><SummaryRow label="Estimasi HPP/unit" value={parseFloat(form.qty_produced) > 0 ? formatRp(estCost / parseFloat(form.qty_produced), true) : "—"} bold tone="primary" /></div>}
        </div>}
      </Modal>
      {detail && <ProductionDetail id={detail} onClose={() => setDetail(null)} />}
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Batalkan produksi ${del?.number}?`} description="Stok bahan akan dikembalikan dan stok produk dikurangi." confirmText="Batalkan Produksi" />
    </div>
  );
}
