import { useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { formatRp, formatNum, formatDate } from "../../lib/format";
import { CrudPage } from "../MasterData";
import { PageHeader, DataTable, Modal, ConfirmDialog, Field, TextInput, NumberInput, SelectInput, TextArea, SummaryRow } from "../../components/common";
import { Button } from "../../components/ui/button";

const PRESETS = ["Solasi + Bubble Wrap", "Solasi + Bubble Wrap + Kardus", "Solasi + Bubble Wrap + Polymailer", "Kardus + Solasi"];

function ConfigForm({ form, setForm, items }) {
  const opts = (items || []).map((i) => ({ value: i.id, label: `${i.name} (${formatRp(i.unit_price, true)}/${i.unit})` }));
  const byId = Object.fromEntries((items || []).map((i) => [i.id, i]));
  const comps = form.components || [];
  const setComp = (idx, patch) => setForm({ ...form, components: comps.map((c, i) => (i === idx ? { ...c, ...patch } : c)) });
  const total = comps.reduce((a, c) => a + (byId[c.item_id]?.unit_price || 0) * (parseFloat(c.qty) || 0), 0);
  return (
    <div className="space-y-4">
      <Field label="Nama Packaging" required hint="Pilih preset atau ketik sendiri">
        <TextInput list="pack-presets" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="packaging-config-name" />
        <datalist id="pack-presets">{PRESETS.map((p) => <option key={p} value={p} />)}</datalist>
      </Field>
      <div>
        <div className="mb-2 flex items-center justify-between"><span className="text-sm font-medium">Komponen</span>
          <Button size="sm" variant="outline" onClick={() => setForm({ ...form, components: [...comps, { item_id: "", qty: 1 }] })} data-testid="packaging-config-add-comp"><Plus className="mr-1 h-4 w-4" />Komponen</Button></div>
        {comps.length === 0 && <p className="text-sm text-muted-foreground">Belum ada komponen. Tambahkan komponen (mis. Solasi, Bubble Wrap, Kardus).</p>}
        <div className="space-y-2">
          {comps.map((c, i) => (
            <div key={i} className="grid grid-cols-[1fr_90px_110px_36px] items-center gap-2" data-testid="packaging-config-comp-row">
              <SelectInput value={c.item_id} onChange={(v) => setComp(i, { item_id: v })} options={opts} placeholder="Pilih komponen" data-testid="packaging-config-comp-item" />
              <NumberInput value={c.qty} onChange={(v) => setComp(i, { qty: v })} placeholder="Qty" data-testid="packaging-config-comp-qty" />
              <span className="num text-right text-sm">{formatRp((byId[c.item_id]?.unit_price || 0) * (parseFloat(c.qty) || 0), true)}</span>
              <Button variant="ghost" size="sm" className="text-red-600" onClick={() => setForm({ ...form, components: comps.filter((_, j) => j !== i) })} data-testid="packaging-config-comp-remove"><Trash2 className="h-4 w-4" /></Button>
            </div>
          ))}
        </div>
      </div>
      <SummaryRow label="Biaya per produk" value={formatRp(total, true)} bold tone="primary" testId="packaging-config-total" />
      <Field label="Keterangan"><TextArea value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} data-testid="packaging-config-notes" /></Field>
    </div>
  );
}

function Configs() {
  const { data, loading, reload } = useApi("/marketplace/packaging/configs");
  const { data: items, reload: reloadItems } = useApi("/marketplace/packaging/items");
  const [form, setForm] = useState(null);
  const [del, setDel] = useState(null);
  const openForm = (f) => { reloadItems(); setForm(f); };
  const save = async () => {
    try {
      const payload = { name: form.name, notes: form.notes, is_active: true, components: (form.components || []).filter((c) => c.item_id).map((c) => ({ item_id: c.item_id, qty: parseFloat(c.qty) || 0 })) };
      if (form.id) await api.put(`/marketplace/packaging/configs/${form.id}`, payload); else await api.post("/marketplace/packaging/configs", payload);
      toast.success("Konfigurasi packaging tersimpan"); setForm(null); reload();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const remove = async () => { try { await api.delete(`/marketplace/packaging/configs/${del.id}`); toast.success("Dihapus"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="packaging-configs-page">
      <PageHeader title="Konfigurasi Packaging" subtitle="Gabungan komponen → biaya packaging per produk. Dikaitkan ke produk/SKU di tabel bawah." actions={<Button onClick={() => openForm({ name: "", components: [{ item_id: "", qty: 1 }], notes: "" })} data-testid="packaging-config-add-btn"><Plus className="mr-1 h-4 w-4" />Tambah Konfigurasi</Button>} />
      <DataTable loading={loading} rows={data || []} filename="Konfigurasi Packaging" testId="packaging-configs-table" columns={[
        { key: "name", label: "Nama Packaging" }, { key: "components", label: "Komponen", render: (r) => r.components.map((c) => `${c.item_name} ×${formatNum(c.qty)}`).join(" + "), export: (r) => r.components.map((c) => `${c.item_name} x${c.qty}`).join(" + ") },
        { key: "cost_per_product", label: "Biaya / Produk", align: "right", render: (r) => formatRp(r.cost_per_product, true) },
        { key: "products", label: "Dipakai Produk", render: (r) => (r.products.length ? r.products.map((p) => p.name).join(", ") : <span className="text-muted-foreground">-</span>), export: (r) => r.products.map((p) => p.name).join(", ") },
        { label: "Aksi", noExport: true, align: "right", render: (r) => <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => openForm({ ...r })} data-testid="packaging-config-edit-btn"><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="packaging-config-delete-btn"><Trash2 className="h-4 w-4" /></Button></div> },
      ]} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? "Edit Konfigurasi Packaging" : "Tambah Konfigurasi Packaging"} footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} data-testid="packaging-config-save-btn">Simpan</Button></>}>
        {form && <ConfigForm form={form} setForm={setForm} items={items} />}
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Hapus ${del?.name}?`} description="Produk yang memakai konfigurasi ini akan kehilangan biaya packaging otomatis." />
    </div>
  );
}

function ProductAssignment() {
  const { data: products, loading, reload } = useApi("/products");
  const { data: cfgs } = useApi("/marketplace/packaging/configs");
  const opts = (cfgs || []).map((c) => ({ value: c.id, label: `${c.name} — ${formatRp(c.cost_per_product, true)}` }));
  const byId = Object.fromEntries((cfgs || []).map((c) => [c.id, c]));
  const assign = async (p, cid) => {
    try { await api.put("/marketplace/packaging/assign", { product_id: p.id, packaging_cost_id: cid || null }); toast.success(`Packaging ${p.name} diperbarui`); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="card-panel" data-testid="packaging-assign-panel">
      <h3 className="mb-1 font-heading font-semibold">Packaging per Produk / SKU</h3>
      <p className="mb-4 text-sm text-muted-foreground">Satu produk memakai satu konfigurasi. Saat ada pesanan, Biaya Beban Packaging = biaya per produk × qty dan ditampilkan <b>terpisah dari HPP</b>. Bila resep produk sudah memuat biaya "Kemasan", jangan pasang konfigurasi di sini agar tidak dihitung dua kali.</p>
      <DataTable loading={loading} rows={products || []} filename="Packaging per Produk" testId="packaging-assign-table" pageSize={15} columns={[
        { key: "sku", label: "SKU", render: (r) => r.sku || "-" }, { key: "name", label: "Produk" }, { key: "avg_hpp", label: "HPP Rata-rata", align: "right", render: (r) => formatRp(r.avg_hpp) },
        { key: "packaging_cost_id", label: "Konfigurasi Packaging", noExport: true, render: (r) => <SelectInput value={r.packaging_cost_id || ""} onChange={(v) => assign(r, v)} options={opts} placeholder="— tanpa packaging —" data-testid={`packaging-assign-select-${r.id}`} className="h-9 min-w-[220px]" /> },
        { label: "Packaging", key: (r) => byId[r.packaging_cost_id]?.name || "-", export: (r) => byId[r.packaging_cost_id]?.name || "-", className: "hidden" },
        { label: "Biaya Packaging / Unit", align: "right", key: (r) => byId[r.packaging_cost_id]?.cost_per_product || 0, render: (r) => <span data-testid={`packaging-assign-cost-${r.id}`}>{formatRp(byId[r.packaging_cost_id]?.cost_per_product || 0, true)}</span> },
      ]} />
    </div>
  );
}

export default function Packaging() {
  return (
    <div className="space-y-10">
      <div>
        <CrudPage title="Komponen Packaging" subtitle="Bahan packaging yang dibeli: harga beli ÷ qty/isi = harga per satuan" endpoint="/marketplace/packaging/items" testId="packaging-items"
          emptyForm={{ name: "", supplier_name: "", purchase_price: "", purchase_qty: "", unit: "pcs", date: "", notes: "" }}
          columns={[
            { key: "name", label: "Komponen" }, { key: "supplier_name", label: "Supplier", render: (r) => r.supplier_name || "-" }, { key: "purchase_price", label: "Harga Beli", align: "right", render: (r) => formatRp(r.purchase_price) },
            { key: "purchase_qty", label: "Qty/Isi", align: "right", render: (r) => `${formatNum(r.purchase_qty)} ${r.unit}` }, { key: "unit_price", label: "Harga / Satuan", align: "right", render: (r) => formatRp(r.unit_price, true) },
            { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) },
          ]}
          fields={[
            { name: "name", label: "Nama Komponen", required: true, hint: "Solasi, Bubble Wrap, Kardus, Polymailer" }, { name: "supplier_name", label: "Supplier" }, { name: "purchase_price", label: "Harga Beli (Rp)", type: "number", required: true },
            { name: "purchase_qty", label: "Qty / Isi Pembelian", type: "number", required: true, hint: "contoh: 1 roll solasi = 6600 cm → isi 6600" }, { name: "unit", label: "Satuan", required: true, hint: "cm, pcs, lembar, meter" },
            { name: "date", label: "Tanggal Beli", type: "date" }, { name: "notes", label: "Keterangan", full: true },
          ]}
          validate={(f) => (!f.name?.trim() ? "Nama wajib diisi" : !(parseFloat(f.purchase_qty) > 0) ? "Qty/isi harus lebih dari 0" : null)}
          transformOut={(f) => ({ ...f, purchase_price: parseFloat(f.purchase_price) || 0, purchase_qty: parseFloat(f.purchase_qty) || 0, date: f.date || null })} />
      </div>
      <Configs />
      <ProductAssignment />
    </div>
  );
}
