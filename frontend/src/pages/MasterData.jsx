import { useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Eye, Upload } from "lucide-react";
import { api, errMsg, fileUrl } from "../lib/api";
import { useApi } from "../lib/hooks";
import { formatRp, formatNum, formatDate } from "../lib/format";
import { PageHeader, DataTable, Modal, ConfirmDialog, Field, TextInput, NumberInput, TextArea, SelectInput, SummaryRow } from "../components/common";
import { Button } from "../components/ui/button";

export function CrudPage({ title, subtitle, endpoint, columns, fields, emptyForm, testId, renderDetail, extraColumns = [], validate, transformOut }) {
  const { data, loading, reload } = useApi(endpoint);
  const [form, setForm] = useState(null);
  const [del, setDel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [saving, setSaving] = useState(false);
  const save = async () => {
    try {
      if (validate) { const err = validate(form); if (err) return toast.error(err); }
      setSaving(true);
      const payload = transformOut ? transformOut(form) : form;
      if (form.id) await api.put(`${endpoint}/${form.id}`, payload); else await api.post(endpoint, payload);
      toast.success("Data tersimpan");
      setForm(null);
      reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  const remove = async () => {
    try { await api.delete(`${endpoint}/${del.id}`); toast.success("Data dihapus"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const cols = [...columns, ...extraColumns, {
    label: "Aksi", noExport: true, render: (r) => (
      <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
        {renderDetail && <Button variant="ghost" size="sm" onClick={() => setDetail(r)} data-testid={`${testId}-detail-btn`}><Eye className="h-4 w-4" /></Button>}
        <Button variant="ghost" size="sm" onClick={() => setForm({ ...emptyForm, ...r })} data-testid={`${testId}-edit-btn`}><Pencil className="h-4 w-4" /></Button>
        <Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid={`${testId}-delete-btn`}><Trash2 className="h-4 w-4" /></Button>
      </div>), align: "right",
  }];
  return (
    <div data-testid={`${testId}-page`}>
      <PageHeader title={title} subtitle={subtitle} actions={<Button onClick={() => setForm({ ...emptyForm })} data-testid={`${testId}-add-btn`}><Plus className="mr-1 h-4 w-4" />Tambah</Button>} />
      <DataTable columns={cols} rows={data || []} loading={loading} filename={title} testId={`${testId}-table`} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? `Edit ${title}` : `Tambah ${title}`} wide={fields.length > 6}
        footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} disabled={saving} data-testid={`${testId}-save-btn`}>Simpan</Button></>}>
        {form && <div className={`grid gap-4 ${fields.length > 6 ? "sm:grid-cols-2" : ""}`}>{fields.map((f) => <FormField key={f.name} f={f} form={form} setForm={setForm} testId={testId} />)}</div>}
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Hapus ${del?.name || del?.code || ""}?`} description="Data akan dihapus (soft delete) dan tidak muncul lagi di daftar." />
      {renderDetail && detail && renderDetail(detail, () => setDetail(null))}
    </div>
  );
}

export function FormField({ f, form, setForm, testId }) {
  const v = form[f.name];
  const set = (val) => setForm({ ...form, [f.name]: val });
  const opts = typeof f.options === "function" ? f.options(form) : f.options;
  const tid = `${testId}-${f.name}-input`;
  if (f.type === "checkbox") return <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={!!v} onChange={(e) => set(e.target.checked)} data-testid={tid} className="h-4 w-4 accent-teal-700" />{f.label}</label>;
  return (
    <Field label={f.label} required={f.required} hint={typeof f.hint === "function" ? f.hint(form) : f.hint} className={f.full ? "sm:col-span-2" : ""}>
      {f.type === "number" ? <NumberInput value={v} onChange={set} data-testid={tid} />
        : f.type === "select" ? <SelectInput value={v} onChange={set} options={opts || []} data-testid={tid} />
        : f.type === "textarea" ? <TextArea value={v || ""} onChange={(e) => set(e.target.value)} data-testid={tid} />
        : f.type === "custom" ? f.render(form, setForm)
        : <TextInput type={f.type || "text"} value={v || ""} onChange={(e) => set(e.target.value)} data-testid={tid} />}
    </Field>
  );
}

const StatusBadge = ({ ok }) => <span className={ok ? "badge-ok" : "badge-muted"}>{ok ? "Aktif" : "Nonaktif"}</span>;

export function Categories() {
  return <CrudPage title="Kategori" subtitle="Kategori bahan baku dan produk" endpoint="/categories" testId="categories" emptyForm={{ name: "", type: "material" }}
    columns={[{ key: "name", label: "Nama" }, { key: "type", label: "Tipe", render: (r) => (r.type === "material" ? "Bahan Baku" : "Produk") }]}
    fields={[{ name: "name", label: "Nama Kategori", required: true }, { name: "type", label: "Tipe", type: "select", options: [{ value: "material", label: "Bahan Baku" }, { value: "product", label: "Produk" }] }]} />;
}

export function Units() {
  const { data: conv, reload } = useApi("/unit-conversions");
  const { data: units } = useApi("/units");
  const [c, setC] = useState({ from_unit: "", to_unit: "", factor: "" });
  const unitOpts = (units || []).map((u) => ({ value: u.code, label: u.code }));
  const addConv = async () => {
    try { await api.post("/unit-conversions", { ...c, factor: parseFloat(c.factor) }); toast.success("Konversi tersimpan"); setC({ from_unit: "", to_unit: "", factor: "" }); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="space-y-8">
      <CrudPage title="Satuan" subtitle="Satuan pembelian & penggunaan (kg, gram, liter, ml, pcs, ...)" endpoint="/units" testId="units" emptyForm={{ code: "", name: "" }}
        columns={[{ key: "code", label: "Kode" }, { key: "name", label: "Nama" }]} fields={[{ name: "code", label: "Kode Satuan", required: true, hint: "contoh: kg, gram, ml" }, { name: "name", label: "Nama" }]} />
      <div className="card-panel" data-testid="unit-conversions-panel">
        <h3 className="mb-3 font-heading font-semibold">Konversi Satuan Umum</h3>
        <p className="mb-4 text-sm text-muted-foreground">Konversi ini digunakan bila satuan pada resep/pembelian berbeda dari satuan bahan. Faktor konversi spesifik per bahan diatur di master Bahan Baku.</p>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Dari"><SelectInput value={c.from_unit} onChange={(v) => setC({ ...c, from_unit: v })} options={unitOpts} data-testid="conv-from-input" /></Field>
          <Field label="Ke"><SelectInput value={c.to_unit} onChange={(v) => setC({ ...c, to_unit: v })} options={unitOpts} data-testid="conv-to-input" /></Field>
          <Field label="Faktor" hint="1 [dari] = faktor [ke]"><NumberInput value={c.factor} onChange={(v) => setC({ ...c, factor: v })} data-testid="conv-factor-input" /></Field>
          <div className="flex items-end"><Button onClick={addConv} disabled={!c.from_unit || !c.to_unit || !c.factor} data-testid="conv-add-btn">Tambah</Button></div>
        </div>
        <ul className="mt-4 divide-y text-sm">{(conv || []).map((x) => (
          <li key={x.id} className="flex items-center justify-between py-2"><span>1 {x.from_unit} = <b className="num">{formatNum(x.factor, 4)}</b> {x.to_unit}</span>
            <Button variant="ghost" size="sm" className="text-red-600" onClick={async () => { await api.delete(`/unit-conversions/${x.id}`); reload(); }} data-testid="conv-delete-btn"><Trash2 className="h-4 w-4" /></Button></li>))}</ul>
      </div>
    </div>
  );
}

function SupplierDetail({ s, onClose }) {
  const { data } = useApi(`/suppliers/${s.id}/purchases`);
  return (
    <Modal open onClose={onClose} title={`Histori Pembelian - ${s.name}`} wide>
      <div className="grid grid-cols-2 gap-3 text-sm"><SummaryRow label="Total transaksi" value={data?.count ?? "-"} /><SummaryRow label="Total pembelian" value={formatRp(data?.total)} /></div>
      <DataTable testId="supplier-purchases" pageSize={8} filename={`pembelian-${s.name}`} rows={data?.purchases || []} columns={[
        { key: "number", label: "Nomor" }, { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { label: "Item", key: (r) => r.items.map((i) => `${i.material_name} ${formatNum(i.qty)} ${i.unit}`).join(", ") },
        { key: "total", label: "Total", align: "right", render: (r) => formatRp(r.total) }, { key: "payment_status", label: "Status", render: (r) => r.payment_status === "paid" ? <span className="badge-ok">Lunas</span> : <span className="badge-low">{r.payment_status === "partial" ? "Sebagian" : "Belum bayar"}</span> }]} />
    </Modal>
  );
}

export function Suppliers() {
  return <CrudPage title="Supplier" subtitle="Data pemasok bahan baku" endpoint="/suppliers" testId="suppliers"
    emptyForm={{ code: "", name: "", contact_name: "", phone: "", email: "", address: "", notes: "", is_active: true }}
    columns={[{ key: "code", label: "Kode" }, { key: "name", label: "Nama Supplier" }, { key: "contact_name", label: "Kontak" }, { key: "phone", label: "Telepon" }, { key: "email", label: "Email" }, { key: "is_active", label: "Status", render: (r) => <StatusBadge ok={r.is_active} /> }]}
    fields={[{ name: "code", label: "Kode Supplier" }, { name: "name", label: "Nama Supplier", required: true }, { name: "contact_name", label: "Nama Kontak" }, { name: "phone", label: "Nomor Telepon" }, { name: "email", label: "Email", type: "email" }, { name: "address", label: "Alamat", type: "textarea" }, { name: "notes", label: "Catatan", type: "textarea" }, { name: "is_active", label: "Aktif", type: "checkbox" }]}
    renderDetail={(s, close) => <SupplierDetail s={s} onClose={close} />} />;
}

function MaterialDetail({ m, onClose }) {
  const { data } = useApi(`/materials/${m.id}`);
  return (
    <Modal open onClose={onClose} title={`${m.name} — Histori Harga & Stok`} wide>
      <div className="grid gap-2 sm:grid-cols-3 text-sm">
        <SummaryRow label="Harga terakhir" value={`${formatRp(m.last_price)}/${m.purchase_unit}`} /><SummaryRow label="Harga rata-rata" value={`${formatRp(m.avg_price, true)}/${m.purchase_unit}`} /><SummaryRow label={`Harga per ${m.usage_unit}`} value={formatRp(m.price_per_usage, true)} />
      </div>
      <h4 className="font-semibold text-sm">Histori Harga (tidak dihapus)</h4>
      <DataTable testId="price-history" pageSize={5} filename={`harga-${m.name}`} rows={data?.price_history || []} columns={[{ key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "price", label: "Harga", align: "right", render: (r) => `${formatRp(r.price)}/${r.unit}` }, { key: "supplier_name", label: "Supplier" }, { key: "source", label: "Sumber", render: (r) => (r.source === "purchase" ? "Pembelian" : "Manual") }]} />
      <h4 className="font-semibold text-sm">Kartu Stok (ledger)</h4>
      <DataTable testId="material-ledger" pageSize={5} filename={`stok-${m.name}`} rows={data?.ledger || []} columns={[{ key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "reason", label: "Jenis" }, { key: "direction", label: "Arah", render: (r) => (r.direction === "in" ? <span className="badge-ok">Masuk</span> : <span className="badge-low">Keluar</span>) }, { key: "qty", label: "Qty", align: "right", render: (r) => `${formatNum(r.qty)} ${r.unit}` }, { key: "balance_after", label: "Saldo", align: "right", render: (r) => formatNum(r.balance_after) }, { key: "note", label: "Catatan" }]} />
    </Modal>
  );
}

export function Materials() {
  const { data: cats } = useApi("/categories?type=material");
  const { data: units } = useApi("/units");
  const { data: sups } = useApi("/suppliers");
  const unitOpts = (units || []).map((u) => ({ value: u.code, label: u.code }));
  return <CrudPage title="Bahan Baku" subtitle="Master bahan dengan konversi satuan, harga & stok minimum" endpoint="/materials" testId="materials"
    emptyForm={{ code: "", name: "", category_id: "", purchase_unit: "kg", usage_unit: "gram", conversion_factor: 1000, last_price: 0, supplier_id: "", min_stock: 0, initial_stock: 0, is_active: true, notes: "" }}
    validate={(f) => (!f.name ? "Nama bahan wajib diisi" : !f.purchase_unit || !f.usage_unit ? "Satuan wajib diisi" : parseFloat(f.conversion_factor) <= 0 ? "Faktor konversi harus > 0" : null)}
    transformOut={(f) => ({ ...f, category_id: f.category_id || null, supplier_id: f.supplier_id || null, conversion_factor: parseFloat(f.conversion_factor), last_price: parseFloat(f.last_price || 0), min_stock: parseFloat(f.min_stock || 0), initial_stock: parseFloat(f.initial_stock || 0) })}
    columns={[{ key: "code", label: "Kode" }, { key: "name", label: "Nama Bahan" }, { label: "Kategori", key: (r) => (cats || []).find((c) => c.id === r.category_id)?.name || "-" },
      { label: "Satuan", key: (r) => `${r.purchase_unit} → ${r.usage_unit} (×${formatNum(r.conversion_factor, 4)})` },
      { key: "last_price", label: "Harga Beli Terakhir", align: "right", render: (r) => `${formatRp(r.last_price)}/${r.purchase_unit}` },
      { key: "price_per_usage", label: "Harga/Satuan Pakai", align: "right", render: (r) => `${formatRp(r.price_per_usage, true)}/${r.usage_unit}` },
      { key: "stock", label: "Stok", align: "right", render: (r) => <span className={r.is_low_stock ? "text-orange-600 font-semibold" : ""}>{formatNum(r.stock)} {r.usage_unit}{r.is_low_stock && <span className="ml-1 badge-low">Rendah</span>}</span> },
      { key: "min_stock", label: "Min", align: "right", render: (r) => formatNum(r.min_stock) }, { key: "stock_value", label: "Nilai Stok", align: "right", render: (r) => formatRp(r.stock_value) },
      { key: "is_active", label: "Status", render: (r) => <StatusBadge ok={r.is_active} /> }]}
    fields={[{ name: "code", label: "Kode Bahan", hint: "Kosongkan untuk otomatis" }, { name: "name", label: "Nama Bahan", required: true },
      { name: "category_id", label: "Kategori", type: "select", options: (cats || []).map((c) => ({ value: c.id, label: c.name })) },
      { name: "supplier_id", label: "Supplier Utama", type: "select", options: (sups || []).map((s) => ({ value: s.id, label: s.name })) },
      { name: "purchase_unit", label: "Satuan Pembelian", type: "select", options: unitOpts, required: true }, { name: "usage_unit", label: "Satuan Penggunaan", type: "select", options: unitOpts, required: true },
      { name: "conversion_factor", label: "Faktor Konversi", type: "number", required: true, hint: (f) => `1 ${f.purchase_unit || "?"} = ${formatNum(f.conversion_factor, 4)} ${f.usage_unit || "?"}` },
      { name: "last_price", label: "Harga Beli Terakhir (per satuan pembelian)", type: "number", hint: (f) => (parseFloat(f.conversion_factor) > 0 ? `= ${formatRp(parseFloat(f.last_price || 0) / parseFloat(f.conversion_factor), true)} per ${f.usage_unit}` : "") },
      { name: "min_stock", label: "Minimum Stok (satuan penggunaan)", type: "number" }, { name: "initial_stock", label: "Stok Awal (hanya saat tambah baru)", type: "number" },
      { name: "notes", label: "Catatan", type: "textarea", full: true }, { name: "is_active", label: "Aktif", type: "checkbox" }]}
    renderDetail={(m, close) => <MaterialDetail m={m} onClose={close} />} />;
}

function PhotoField({ form, setForm, testId }) {
  const [up, setUp] = useState(false);
  const meta = useApi("/meta");
  const disabled = meta.data && !meta.data.storage_enabled;
  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUp(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setForm({ ...form, photo_url: data.url });
      toast.success("Foto terunggah");
    } catch (err) { toast.error(errMsg(err)); } finally { setUp(false); }
  };
  return (
    <div className="flex items-center gap-3">
      {form.photo_url ? <img src={fileUrl(form.photo_url)} alt="" className="h-16 w-16 rounded-lg object-cover border" /> : <div className="h-16 w-16 rounded-lg border bg-muted" />}
      {disabled
        ? <span className="text-xs text-muted-foreground" data-testid={`${testId}-photo-disabled`}>Upload foto nonaktif — penyimpanan file (S3/R2) belum dikonfigurasi di server.</span>
        : <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted"><Upload className="h-4 w-4" />{up ? "Mengunggah..." : "Upload Foto"}<input type="file" accept="image/*" className="hidden" onChange={upload} data-testid={`${testId}-photo-input`} /></label>}
    </div>
  );
}

export function Products() {
  const { data: cats } = useApi("/categories?type=product");
  const { data: units } = useApi("/units");
  return <CrudPage title="Produk" subtitle="Produk jadi yang dijual" endpoint="/products" testId="products"
    emptyForm={{ sku: "", name: "", category_id: "", unit: "pcs", selling_price: 0, photo_url: "", description: "", min_stock: 0, is_active: true }}
    validate={(f) => (!f.name ? "Nama produk wajib diisi" : parseFloat(f.selling_price) < 0 ? "Harga jual tidak boleh negatif" : null)}
    transformOut={(f) => ({ ...f, category_id: f.category_id || null, selling_price: parseFloat(f.selling_price || 0), min_stock: parseFloat(f.min_stock || 0) })}
    columns={[{ label: "Foto", noExport: true, render: (r) => (r.photo_url ? <img src={fileUrl(r.photo_url)} alt="" className="h-10 w-10 rounded-md object-cover border" /> : <div className="h-10 w-10 rounded-md bg-muted" />) },
      { key: "sku", label: "SKU" }, { key: "name", label: "Nama Produk" }, { label: "Kategori", key: (r) => (cats || []).find((c) => c.id === r.category_id)?.name || "-" }, { key: "unit", label: "Satuan" },
      { key: "selling_price", label: "Harga Jual", align: "right", render: (r) => formatRp(r.selling_price) }, { key: "avg_hpp", label: "HPP Rata-rata", align: "right", render: (r) => formatRp(r.avg_hpp, true) },
      { label: "Margin", align: "right", key: (r) => (r.selling_price > 0 && r.avg_hpp > 0 ? `${formatNum(((r.selling_price - r.avg_hpp) / r.selling_price) * 100, 1)}%` : "-") },
      { key: "stock", label: "Stok", align: "right", render: (r) => <span className={r.is_low_stock ? "text-orange-600 font-semibold" : ""}>{formatNum(r.stock)} {r.unit}</span> }, { key: "recipe_count", label: "Resep", align: "right" },
      { key: "is_active", label: "Status", render: (r) => <StatusBadge ok={r.is_active} /> }]}
    fields={[{ name: "sku", label: "SKU", hint: "Kosongkan untuk otomatis" }, { name: "name", label: "Nama Produk", required: true },
      { name: "category_id", label: "Kategori", type: "select", options: (cats || []).map((c) => ({ value: c.id, label: c.name })) }, { name: "unit", label: "Satuan Penjualan", type: "select", options: (units || []).map((u) => ({ value: u.code, label: u.code })) },
      { name: "selling_price", label: "Harga Jual", type: "number" }, { name: "min_stock", label: "Minimum Stok", type: "number" },
      { name: "photo_url", label: "Foto Produk", type: "custom", full: true, render: (form, setForm) => <PhotoField form={form} setForm={setForm} testId="products" /> },
      { name: "description", label: "Deskripsi", type: "textarea", full: true }, { name: "is_active", label: "Aktif", type: "checkbox" }]} />;
}
