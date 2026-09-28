import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Eye, Pencil, Banknote } from "lucide-react";
import { api, errMsg } from "../lib/api";
import { useApi, qs } from "../lib/hooks";
import { formatRp, formatNum, formatDate, todayISO } from "../lib/format";
import { PageHeader, DataTable, Modal, ConfirmDialog, Field, TextInput, NumberInput, SelectInput, TextArea, SummaryRow, PeriodFilter, usePeriod, StatCard } from "../components/common";
import { Button } from "../components/ui/button";

const PayBadge = ({ s }) => (s === "paid" ? <span className="badge-ok">Lunas</span> : <span className="badge-low">{s === "partial" ? "Sebagian" : "Belum bayar"}</span>);

function ItemsTable({ headers, children, footer }) {
  return <div className="table-wrap"><table><thead><tr>{headers.map((h, i) => <th key={i} className={h.right ? "text-right" : ""}>{h.label || h}</th>)}</tr></thead><tbody>{children}</tbody>{footer}</table></div>;
}

// ---------------- PURCHASES ----------------
export function Purchases() {
  const period = usePeriod("all");
  const { data, loading, reload } = useApi(`/purchases${qs(period.range)}`, [period.range.start, period.range.end]);
  const { data: materials } = useApi("/materials");
  const { data: suppliers } = useApi("/suppliers");
  const { data: accounts } = useApi("/cash/accounts");
  const { data: meta } = useApi("/meta");
  const [form, setForm] = useState(null);
  const [detail, setDetail] = useState(null);
  const [pay, setPay] = useState(null);
  const [del, setDel] = useState(null);
  const [saving, setSaving] = useState(false);
  const matMap = Object.fromEntries((materials || []).map((m) => [m.id, m]));
  const newForm = () => ({ date: todayISO(), supplier_id: "", items: [{ material_id: "", qty: "", unit: "", price: "", discount: 0 }], discount: 0, extra_cost: 0, payment_method: "Tunai", payment_status: "paid", cash_account_id: accounts?.[0]?.id || "", notes: "" });
  const editForm = (r) => ({ id: r.id, number: r.number, date: r.date, supplier_id: r.supplier_id || "", items: r.items.map((it) => ({ material_id: it.material_id, qty: it.qty, unit: it.unit, price: it.price, discount: it.discount })), discount: r.discount, extra_cost: r.extra_cost, payment_method: r.payment_method, payment_status: r.payment_status === "partial" ? "unpaid" : r.payment_status, cash_account_id: r.cash_account_id || accounts?.[0]?.id || "", notes: r.notes, was_partial: r.payment_status === "partial" });
  const setItem = (i, patch) => setForm({ ...form, items: form.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const subtotal = form ? form.items.reduce((a, it) => a + (parseFloat(it.qty) || 0) * (parseFloat(it.price) || 0) - (parseFloat(it.discount) || 0), 0) : 0;
  const total = subtotal - (parseFloat(form?.discount) || 0) + (parseFloat(form?.extra_cost) || 0);
  const save = async () => {
    if (form.items.some((it) => !it.material_id || !(parseFloat(it.qty) > 0))) return toast.error("Lengkapi bahan dan qty (> 0) pada setiap baris");
    setSaving(true);
    try {
      const body = { ...form, supplier_id: form.supplier_id || null, cash_account_id: form.cash_account_id || null, discount: parseFloat(form.discount || 0), extra_cost: parseFloat(form.extra_cost || 0), items: form.items.map((it) => ({ material_id: it.material_id, qty: parseFloat(it.qty), unit: it.unit || null, price: parseFloat(it.price || 0), discount: parseFloat(it.discount || 0) })) };
      if (form.id) await api.put(`/purchases/${form.id}`, body); else await api.post("/purchases", body);
      toast.success(form.id ? "Pembelian diperbarui: stok & kas dihitung ulang" : "Pembelian tersimpan: stok & harga bahan diperbarui"); setForm(null); reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  const doPay = async () => {
    try { await api.post(`/purchases/${pay.id}/pay`, { amount: parseFloat(pay.amount), cash_account_id: pay.cash_account_id || null, date: pay.date }); toast.success("Pembayaran tercatat"); setPay(null); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const remove = async () => { try { await api.delete(`/purchases/${del.id}`); toast.success("Pembelian dibatalkan, stok dikembalikan"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const rows = data || [];
  return (
    <div data-testid="purchases-page">
      <PageHeader title="Pembelian" subtitle="Pembelian bahan otomatis menambah stok, mencatat histori harga & hutang" actions={<><PeriodFilter period={period} /><Button onClick={() => setForm(newForm())} data-testid="purchase-add-btn"><Plus className="mr-1 h-4 w-4" />Pembelian Baru</Button></>} />
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3"><StatCard label="Total pembelian" value={formatRp(rows.reduce((a, r) => a + r.total, 0))} testId="purchase-total" /><StatCard label="Transaksi" value={rows.length} /><StatCard label="Hutang belum dibayar" value={formatRp(rows.reduce((a, r) => a + r.total - (r.paid_amount || 0), 0))} tone="accent" testId="purchase-unpaid" /></div>
      <DataTable testId="purchases-table" filename="pembelian" rows={rows} loading={loading} searchKeys={["number", "supplier_name"]} columns={[
        { key: "number", label: "Nomor" }, { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "supplier_name", label: "Supplier" }, { label: "Item", key: (r) => r.items.map((i) => `${i.material_name} ${formatNum(i.qty)} ${i.unit}`).join(", "), className: "max-w-xs truncate" },
        { key: "total", label: "Total", align: "right", render: (r) => formatRp(r.total) }, { key: "paid_amount", label: "Dibayar", align: "right", render: (r) => formatRp(r.paid_amount) }, { key: "payment_method", label: "Metode" }, { key: "payment_status", label: "Status", render: (r) => <PayBadge s={r.payment_status} /> },
        { label: "Aksi", noExport: true, align: "right", render: (r) => <div className="flex justify-end gap-1">{r.payment_status !== "paid" && <Button variant="ghost" size="sm" title="Bayar" onClick={() => setPay({ id: r.id, amount: r.total - (r.paid_amount || 0), cash_account_id: accounts?.[0]?.id || "", date: todayISO() })} data-testid="purchase-pay-btn"><Banknote className="h-4 w-4 text-emerald-600" /></Button>}<Button variant="ghost" size="sm" onClick={() => setDetail(r)} data-testid="purchase-detail-btn"><Eye className="h-4 w-4" /></Button><Button variant="ghost" size="sm" onClick={() => setForm(editForm(r))} data-testid="purchase-edit-btn"><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="purchase-delete-btn"><Trash2 className="h-4 w-4" /></Button></div> },
      ]} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? `Edit Pembelian ${form.number}` : "Pembelian Bahan"} description={form?.id ? "Stok, histori harga, dan kas dari pembelian ini akan dihitung ulang sesuai data baru." : undefined} wide footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} disabled={saving} data-testid="purchase-save-btn">{form?.id ? "Simpan Perubahan" : "Simpan Pembelian"}</Button></>}>
        {form && <>
          {form.was_partial && <p className="rounded-md bg-orange-50 p-2 text-xs text-orange-700">Pembelian ini sebelumnya dibayar sebagian. Pembayaran lama akan dihapus; pilih status Lunas atau catat ulang pembayaran setelah menyimpan.</p>}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Tanggal"><TextInput type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="purchase-date-input" /></Field>
            <Field label="Supplier"><SelectInput value={form.supplier_id} onChange={(v) => setForm({ ...form, supplier_id: v })} options={(suppliers || []).map((s) => ({ value: s.id, label: s.name }))} data-testid="purchase-supplier-select" /></Field>
            <Field label="Metode Pembayaran"><SelectInput value={form.payment_method} onChange={(v) => setForm({ ...form, payment_method: v, payment_status: v === "Kredit/Tempo" ? "unpaid" : form.payment_status })} allowEmpty={false} options={(meta?.payment_methods || []).map((m) => ({ value: m, label: m }))} data-testid="purchase-method-select" /></Field>
          </div>
          <ItemsTable headers={["Bahan", "Qty", "Satuan", { label: "Harga/Satuan", right: true }, { label: "Diskon", right: true }, { label: "Subtotal", right: true }, ""]}>
            {form.items.map((it, i) => { const m = matMap[it.material_id]; return (
              <tr key={i} data-testid="purchase-item-row">
                <td className="min-w-[200px]"><SelectInput value={it.material_id} onChange={(v) => { const mm = matMap[v]; setItem(i, { material_id: v, unit: mm?.purchase_unit || "", price: it.price || mm?.last_price || "" }); }} options={(materials || []).map((m) => ({ value: m.id, label: m.name }))} className="h-9" data-testid="purchase-item-material" /></td>
                <td className="w-24"><NumberInput value={it.qty} onChange={(v) => setItem(i, { qty: v })} className="h-9" data-testid="purchase-item-qty" /></td>
                <td className="w-28"><SelectInput value={it.unit} onChange={(v) => setItem(i, { unit: v })} allowEmpty={false} options={m ? [...new Set([m.purchase_unit, m.usage_unit])].map((u) => ({ value: u, label: u })) : []} className="h-9" data-testid="purchase-item-unit" /></td>
                <td className="w-32"><NumberInput value={it.price} onChange={(v) => setItem(i, { price: v })} className="h-9" data-testid="purchase-item-price" /></td>
                <td className="w-28"><NumberInput value={it.discount} onChange={(v) => setItem(i, { discount: v })} className="h-9" data-testid="purchase-item-discount" /></td>
                <td className="text-right num">{formatRp((parseFloat(it.qty) || 0) * (parseFloat(it.price) || 0) - (parseFloat(it.discount) || 0))}</td>
                <td><Button variant="ghost" size="icon" className="h-8 w-8 text-red-600" onClick={() => setForm({ ...form, items: form.items.filter((_, j) => j !== i) })} disabled={form.items.length === 1} data-testid="purchase-item-delete"><Trash2 className="h-3.5 w-3.5" /></Button></td>
              </tr>); })}
          </ItemsTable>
          <Button variant="outline" size="sm" onClick={() => setForm({ ...form, items: [...form.items, { material_id: "", qty: "", unit: "", price: "", discount: 0 }] })} data-testid="purchase-add-item-btn"><Plus className="mr-1 h-4 w-4" />Tambah Bahan</Button>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Diskon"><NumberInput value={form.discount} onChange={(v) => setForm({ ...form, discount: v })} data-testid="purchase-discount-input" /></Field>
              <Field label="Biaya Tambahan (ongkir dll)"><NumberInput value={form.extra_cost} onChange={(v) => setForm({ ...form, extra_cost: v })} data-testid="purchase-extra-input" /></Field>
              <Field label="Status Pembayaran"><SelectInput value={form.payment_status} onChange={(v) => setForm({ ...form, payment_status: v })} allowEmpty={false} options={[{ value: "paid", label: "Lunas" }, { value: "unpaid", label: "Belum bayar (hutang)" }]} data-testid="purchase-status-select" /></Field>
              {form.payment_status === "paid" && <Field label="Dibayar dari akun"><SelectInput value={form.cash_account_id} onChange={(v) => setForm({ ...form, cash_account_id: v })} options={(accounts || []).map((a) => ({ value: a.id, label: `${a.name} (${formatRp(a.balance)})` }))} data-testid="purchase-account-select" /></Field>}
              <Field label="Catatan" className="sm:col-span-2"><TextInput value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} data-testid="purchase-notes-input" /></Field>
            </div>
            <div className="rounded-lg bg-muted/50 p-4"><SummaryRow label="Subtotal" value={formatRp(subtotal)} /><SummaryRow label="Diskon" value={`- ${formatRp(form.discount)}`} /><SummaryRow label="Biaya tambahan" value={formatRp(form.extra_cost)} /><SummaryRow label="TOTAL" value={formatRp(total)} bold testId="purchase-form-total" /></div>
          </div>
        </>}
      </Modal>
      <Modal open={!!detail} onClose={() => setDetail(null)} title={`${detail?.number} — ${detail?.supplier_name}`} wide>
        {detail && <>
          <ItemsTable headers={["Bahan", { label: "Qty", right: true }, "Satuan", { label: "Harga", right: true }, { label: "Diskon", right: true }, { label: "Subtotal", right: true }]}>
            {detail.items.map((it, i) => <tr key={i}><td>{it.material_name}</td><td className="text-right num">{formatNum(it.qty)}</td><td>{it.unit}</td><td className="text-right num">{formatRp(it.price)}</td><td className="text-right num">{formatRp(it.discount)}</td><td className="text-right num">{formatRp(it.subtotal)}</td></tr>)}
          </ItemsTable>
          <div className="sm:w-72 ml-auto"><SummaryRow label="Subtotal" value={formatRp(detail.subtotal)} /><SummaryRow label="Diskon" value={formatRp(detail.discount)} /><SummaryRow label="Biaya tambahan" value={formatRp(detail.extra_cost)} /><SummaryRow label="Total" value={formatRp(detail.total)} bold /><SummaryRow label="Dibayar" value={formatRp(detail.paid_amount)} /><SummaryRow label="Sisa" value={formatRp(detail.total - detail.paid_amount)} tone="accent" /></div>
        </>}
      </Modal>
      <Modal open={!!pay} onClose={() => setPay(null)} title="Bayar Hutang Pembelian" footer={<><Button variant="outline" onClick={() => setPay(null)}>Batal</Button><Button onClick={doPay} data-testid="pay-save-btn">Bayar</Button></>}>
        {pay && <div className="grid gap-4 sm:grid-cols-2"><Field label="Jumlah"><NumberInput value={pay.amount} onChange={(v) => setPay({ ...pay, amount: v })} data-testid="pay-amount-input" /></Field><Field label="Tanggal"><TextInput type="date" value={pay.date} onChange={(e) => setPay({ ...pay, date: e.target.value })} /></Field><Field label="Dari akun" className="sm:col-span-2"><SelectInput value={pay.cash_account_id} onChange={(v) => setPay({ ...pay, cash_account_id: v })} options={(accounts || []).map((a) => ({ value: a.id, label: a.name }))} /></Field></div>}
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Batalkan pembelian ${del?.number}?`} description="Stok bahan akan dikurangi kembali dan transaksi kas terkait dihapus." confirmText="Batalkan" />
    </div>
  );
}

// ---------------- SALES ----------------
export function Sales() {
  const period = usePeriod("all");
  const { data, loading, reload } = useApi(`/sales${qs(period.range)}`, [period.range.start, period.range.end]);
  const { data: products } = useApi("/products");
  const { data: accounts } = useApi("/cash/accounts");
  const { data: meta } = useApi("/meta");
  const [form, setForm] = useState(null);
  const [detail, setDetail] = useState(null);
  const [del, setDel] = useState(null);
  const [saving, setSaving] = useState(false);
  const prodMap = Object.fromEntries((products || []).map((p) => [p.id, p]));
  const newForm = () => ({ date: todayISO(), channel: "Offline", items: [{ product_id: "", qty: 1, price: "", discount: 0 }], discount: 0, platform_fee: 0, service_fee: 0, other_fee: 0, payment_method: "Tunai", cash_account_id: accounts?.[0]?.id || "", customer: "", notes: "" });
  const editForm = (r) => ({ id: r.id, number: r.number, date: r.date, channel: r.channel, items: r.items.map((it) => ({ product_id: it.product_id, qty: it.qty, price: it.price, discount: it.discount })), discount: r.discount, platform_fee: r.platform_fee, service_fee: r.service_fee, other_fee: r.other_fee, payment_method: r.payment_method, cash_account_id: r.cash_account_id || accounts?.[0]?.id || "", customer: r.customer, notes: r.notes });
  const setItem = (i, patch) => setForm({ ...form, items: form.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const gross = form ? form.items.reduce((a, it) => a + (parseFloat(it.qty) || 0) * (parseFloat(it.price) || 0) - (parseFloat(it.discount) || 0), 0) : 0;
  const total = gross - (parseFloat(form?.discount) || 0);
  const net = total - (parseFloat(form?.platform_fee) || 0) - (parseFloat(form?.service_fee) || 0) - (parseFloat(form?.other_fee) || 0);
  const hpp = form ? form.items.reduce((a, it) => a + (parseFloat(it.qty) || 0) * (prodMap[it.product_id]?.avg_hpp || 0), 0) : 0;
  const save = async () => {
    if (form.items.some((it) => !it.product_id || !(parseFloat(it.qty) > 0))) return toast.error("Lengkapi produk dan qty (> 0) pada setiap baris");
    setSaving(true);
    try {
      const body = { ...form, cash_account_id: form.cash_account_id || null, discount: parseFloat(form.discount || 0), platform_fee: parseFloat(form.platform_fee || 0), service_fee: parseFloat(form.service_fee || 0), other_fee: parseFloat(form.other_fee || 0), items: form.items.map((it) => ({ product_id: it.product_id, qty: parseFloat(it.qty), price: parseFloat(it.price || 0), discount: parseFloat(it.discount || 0) })) };
      if (form.id) await api.put(`/sales/${form.id}`, body); else await api.post("/sales", body);
      toast.success(form.id ? "Penjualan diperbarui: stok & kas dihitung ulang" : "Penjualan tersimpan: stok produk berkurang, kas bertambah"); setForm(null); reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  const remove = async () => { try { await api.delete(`/sales/${del.id}`); toast.success("Penjualan dibatalkan, stok dikembalikan"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const rows = data || [];
  return (
    <div data-testid="sales-page">
      <PageHeader title="Penjualan" subtitle="Setiap penjualan mengurangi stok, mencatat HPP penjualan & laba" actions={<><PeriodFilter period={period} /><Button onClick={() => setForm(newForm())} data-testid="sale-add-btn"><Plus className="mr-1 h-4 w-4" />Penjualan Baru</Button></>} />
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4"><StatCard label="Omzet bersih" value={formatRp(rows.reduce((a, r) => a + r.net_total, 0))} tone="primary" testId="sales-total" /><StatCard label="HPP penjualan" value={formatRp(rows.reduce((a, r) => a + r.total_hpp, 0))} /><StatCard label="Laba kotor" value={formatRp(rows.reduce((a, r) => a + r.profit, 0))} tone="good" testId="sales-profit" /><StatCard label="Transaksi" value={rows.length} /></div>
      <DataTable testId="sales-table" filename="penjualan" rows={rows} loading={loading} searchKeys={["number", "channel", "customer"]} columns={[
        { key: "number", label: "Nomor" }, { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "channel", label: "Channel", render: (r) => <span className="badge-muted">{r.channel}</span> }, { label: "Produk", key: (r) => r.items.map((i) => `${i.product_name} ×${formatNum(i.qty)}`).join(", "), className: "max-w-xs truncate" },
        { key: "qty_total", label: "Qty", align: "right" }, { key: "total", label: "Total", align: "right", render: (r) => formatRp(r.total) }, { label: "Biaya", align: "right", key: (r) => formatRp(r.platform_fee + r.service_fee + r.other_fee) }, { key: "net_total", label: "Bersih", align: "right", render: (r) => formatRp(r.net_total) },
        { key: "total_hpp", label: "HPP", align: "right", render: (r) => formatRp(r.total_hpp) }, { key: "profit", label: "Laba", align: "right", render: (r) => <span className={r.profit >= 0 ? "text-emerald-700" : "text-red-600"}>{formatRp(r.profit)}</span> },
        { label: "Aksi", noExport: true, align: "right", render: (r) => <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => setDetail(r)} data-testid="sale-detail-btn"><Eye className="h-4 w-4" /></Button><Button variant="ghost" size="sm" onClick={() => setForm(editForm(r))} data-testid="sale-edit-btn"><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="sale-delete-btn"><Trash2 className="h-4 w-4" /></Button></div> },
      ]} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? `Edit Penjualan ${form.number}` : "Transaksi Penjualan"} description={form?.id ? "Stok produk dan kas dari penjualan ini akan dihitung ulang sesuai data baru." : undefined} wide footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} disabled={saving} data-testid="sale-save-btn">{form?.id ? "Simpan Perubahan" : "Simpan Penjualan"}</Button></>}>
        {form && <>
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Tanggal"><TextInput type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="sale-date-input" /></Field>
            <Field label="Channel"><SelectInput value={form.channel} onChange={(v) => setForm({ ...form, channel: v })} allowEmpty={false} options={(meta?.channels || []).map((c) => ({ value: c, label: c }))} data-testid="sale-channel-select" /></Field>
            <Field label="Metode Bayar"><SelectInput value={form.payment_method} onChange={(v) => setForm({ ...form, payment_method: v })} allowEmpty={false} options={(meta?.payment_methods || []).map((m) => ({ value: m, label: m }))} data-testid="sale-method-select" /></Field>
            <Field label="Masuk ke akun"><SelectInput value={form.cash_account_id} onChange={(v) => setForm({ ...form, cash_account_id: v })} options={(accounts || []).map((a) => ({ value: a.id, label: a.name }))} data-testid="sale-account-select" /></Field>
          </div>
          <ItemsTable headers={["Produk", "Qty", { label: "Harga", right: true }, { label: "Diskon", right: true }, { label: "Subtotal", right: true }, { label: "HPP", right: true }, ""]}>
            {form.items.map((it, i) => { const p = prodMap[it.product_id]; return (
              <tr key={i} data-testid="sale-item-row">
                <td className="min-w-[200px]"><SelectInput value={it.product_id} onChange={(v) => setItem(i, { product_id: v, price: prodMap[v]?.selling_price ?? "" })} options={(products || []).map((p) => ({ value: p.id, label: `${p.name} (stok ${formatNum(p.stock)})` }))} className="h-9" data-testid="sale-item-product" />{p && !form.id && parseFloat(it.qty) > p.stock && <p className="text-[11px] text-red-600">Stok tidak cukup (tersedia {formatNum(p.stock)})</p>}</td>
                <td className="w-24"><NumberInput value={it.qty} onChange={(v) => setItem(i, { qty: v })} className="h-9" data-testid="sale-item-qty" /></td>
                <td className="w-32"><NumberInput value={it.price} onChange={(v) => setItem(i, { price: v })} className="h-9" data-testid="sale-item-price" /></td>
                <td className="w-28"><NumberInput value={it.discount} onChange={(v) => setItem(i, { discount: v })} className="h-9" data-testid="sale-item-discount" /></td>
                <td className="text-right num">{formatRp((parseFloat(it.qty) || 0) * (parseFloat(it.price) || 0) - (parseFloat(it.discount) || 0))}</td>
                <td className="text-right num text-xs text-muted-foreground">{formatRp((parseFloat(it.qty) || 0) * (p?.avg_hpp || 0))}</td>
                <td><Button variant="ghost" size="icon" className="h-8 w-8 text-red-600" onClick={() => setForm({ ...form, items: form.items.filter((_, j) => j !== i) })} disabled={form.items.length === 1} data-testid="sale-item-delete"><Trash2 className="h-3.5 w-3.5" /></Button></td>
              </tr>); })}
          </ItemsTable>
          <Button variant="outline" size="sm" onClick={() => setForm({ ...form, items: [...form.items, { product_id: "", qty: 1, price: "", discount: 0 }] })} data-testid="sale-add-item-btn"><Plus className="mr-1 h-4 w-4" />Tambah Produk</Button>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Diskon transaksi"><NumberInput value={form.discount} onChange={(v) => setForm({ ...form, discount: v })} data-testid="sale-discount-input" /></Field>
              <Field label="Biaya platform"><NumberInput value={form.platform_fee} onChange={(v) => setForm({ ...form, platform_fee: v })} data-testid="sale-platform-fee-input" /></Field>
              <Field label="Biaya layanan"><NumberInput value={form.service_fee} onChange={(v) => setForm({ ...form, service_fee: v })} data-testid="sale-service-fee-input" /></Field>
              <Field label="Biaya lainnya"><NumberInput value={form.other_fee} onChange={(v) => setForm({ ...form, other_fee: v })} data-testid="sale-other-fee-input" /></Field>
              <Field label="Pelanggan"><TextInput value={form.customer} onChange={(e) => setForm({ ...form, customer: e.target.value })} data-testid="sale-customer-input" /></Field>
              <Field label="Catatan"><TextInput value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
            </div>
            <div className="rounded-lg bg-muted/50 p-4"><SummaryRow label="Subtotal" value={formatRp(gross)} /><SummaryRow label="Diskon" value={`- ${formatRp(form.discount)}`} /><SummaryRow label="Total" value={formatRp(total)} /><SummaryRow label="Biaya platform/layanan/lain" value={`- ${formatRp((parseFloat(form.platform_fee) || 0) + (parseFloat(form.service_fee) || 0) + (parseFloat(form.other_fee) || 0))}`} /><SummaryRow label="PENJUALAN BERSIH" value={formatRp(net)} bold testId="sale-form-net" /><SummaryRow label="HPP" value={formatRp(hpp)} /><SummaryRow label="LABA" value={formatRp(net - hpp)} bold tone={net - hpp >= 0 ? "good" : "bad"} testId="sale-form-profit" /></div>
          </div>
        </>}
      </Modal>
      <Modal open={!!detail} onClose={() => setDetail(null)} title={`${detail?.number} — ${detail?.channel}`} wide>
        {detail && <>
          <ItemsTable headers={["Produk", { label: "Qty", right: true }, { label: "Harga", right: true }, { label: "Diskon", right: true }, { label: "Subtotal", right: true }, { label: "HPP/unit", right: true }, { label: "Laba", right: true }]}>
            {detail.items.map((it, i) => <tr key={i}><td>{it.product_name}</td><td className="text-right num">{formatNum(it.qty)}</td><td className="text-right num">{formatRp(it.price)}</td><td className="text-right num">{formatRp(it.discount)}</td><td className="text-right num">{formatRp(it.subtotal)}</td><td className="text-right num">{formatRp(it.hpp_unit, true)}</td><td className="text-right num">{formatRp(it.profit)}</td></tr>)}
          </ItemsTable>
          <div className="sm:w-72 ml-auto"><SummaryRow label="Total" value={formatRp(detail.total)} /><SummaryRow label="Biaya platform" value={formatRp(detail.platform_fee)} /><SummaryRow label="Biaya layanan" value={formatRp(detail.service_fee)} /><SummaryRow label="Biaya lainnya" value={formatRp(detail.other_fee)} /><SummaryRow label="Penjualan bersih" value={formatRp(detail.net_total)} bold /><SummaryRow label="HPP" value={formatRp(detail.total_hpp)} /><SummaryRow label="Laba" value={formatRp(detail.profit)} bold tone="good" /></div>
        </>}
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Batalkan penjualan ${del?.number}?`} description="Stok produk dikembalikan dan pemasukan kas terkait dihapus." confirmText="Batalkan" />
    </div>
  );
}

// ---------------- EXPENSES ----------------
export function Expenses() {
  const period = usePeriod("month");
  const { data, loading, reload } = useApi(`/expenses${qs(period.range)}`, [period.range.start, period.range.end]);
  const { data: accounts } = useApi("/cash/accounts");
  const { data: meta } = useApi("/meta");
  const [form, setForm] = useState(null);
  const [del, setDel] = useState(null);
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!form.description?.trim()) return toast.error("Deskripsi wajib diisi");
    if (!(parseFloat(form.amount) > 0)) return toast.error("Nominal harus lebih dari 0");
    setSaving(true);
    try {
      const body = { ...form, amount: parseFloat(form.amount), cash_account_id: form.cash_account_id || null };
      if (form.id) await api.put(`/expenses/${form.id}`, body); else await api.post("/expenses", body);
      toast.success("Pengeluaran tersimpan"); setForm(null); reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  const upload = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    try { const fd = new FormData(); fd.append("file", file); const { data } = await api.post("/upload", fd); setForm({ ...form, receipt_url: data.url }); toast.success("Bukti terunggah"); } catch (err) { toast.error(errMsg(err)); }
  };
  const remove = async () => { try { await api.delete(`/expenses/${del.id}`); toast.success("Pengeluaran dihapus"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const rows = data || [];
  return (
    <div data-testid="expenses-page">
      <PageHeader title="Pengeluaran" subtitle="Biaya operasional di luar pembelian bahan" actions={<><PeriodFilter period={period} /><Button onClick={() => setForm({ date: todayISO(), category: "Operasional", description: "", amount: "", payment_method: "Tunai", cash_account_id: accounts?.[0]?.id || "", receipt_url: "", notes: "" })} data-testid="expense-add-btn"><Plus className="mr-1 h-4 w-4" />Tambah</Button></>} />
      <div className="mb-4 grid grid-cols-2 gap-3"><StatCard label="Total pengeluaran (periode)" value={formatRp(rows.reduce((a, r) => a + r.amount, 0))} tone="accent" testId="expenses-total" /><StatCard label="Jumlah" value={rows.length} /></div>
      <DataTable testId="expenses-table" filename="pengeluaran" rows={rows} loading={loading} searchKeys={["description", "category", "number"]} columns={[
        { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "number", label: "Nomor" }, { key: "category", label: "Kategori", render: (r) => <span className="badge-muted">{r.category}</span> }, { key: "description", label: "Deskripsi" },
        { key: "amount", label: "Nominal", align: "right", render: (r) => <b>{formatRp(r.amount)}</b> }, { key: "payment_method", label: "Metode" }, { label: "Bukti", noExport: true, render: (r) => (r.receipt_url ? <a href={`${process.env.REACT_APP_BACKEND_URL}${r.receipt_url}?auth=${localStorage.getItem("token")}`} target="_blank" rel="noreferrer" className="text-primary underline text-xs">Lihat</a> : "-") },
        { label: "Aksi", noExport: true, align: "right", render: (r) => <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => setForm({ ...r })} data-testid="expense-edit-btn"><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="expense-delete-btn"><Trash2 className="h-4 w-4" /></Button></div> },
      ]} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? "Edit Pengeluaran" : "Tambah Pengeluaran"} footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} disabled={saving} data-testid="expense-save-btn">Simpan</Button></>}>
        {form && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tanggal"><TextInput type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="expense-date-input" /></Field>
          <Field label="Kategori"><SelectInput value={form.category} onChange={(v) => setForm({ ...form, category: v })} allowEmpty={false} options={(meta?.expense_categories || []).map((c) => ({ value: c, label: c }))} data-testid="expense-category-select" /></Field>
          <Field label="Deskripsi" required className="sm:col-span-2"><TextInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="expense-description-input" /></Field>
          <Field label="Nominal" required><NumberInput value={form.amount} onChange={(v) => setForm({ ...form, amount: v })} data-testid="expense-amount-input" /></Field>
          <Field label="Metode Pembayaran"><SelectInput value={form.payment_method} onChange={(v) => setForm({ ...form, payment_method: v })} allowEmpty={false} options={(meta?.payment_methods || []).map((m) => ({ value: m, label: m }))} data-testid="expense-method-select" /></Field>
          <Field label="Dari akun kas"><SelectInput value={form.cash_account_id} onChange={(v) => setForm({ ...form, cash_account_id: v })} options={(accounts || []).map((a) => ({ value: a.id, label: a.name }))} data-testid="expense-account-select" /></Field>
          <Field label="Bukti (foto/pdf)"><input type="file" accept="image/*,application/pdf" onChange={upload} className="text-sm" data-testid="expense-receipt-input" />{form.receipt_url && <span className="text-xs text-emerald-700">Bukti terlampir</span>}</Field>
          <Field label="Catatan" className="sm:col-span-2"><TextArea value={form.notes || ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
        </div>}
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title="Hapus pengeluaran?" description="Transaksi kas terkait juga akan dihapus." />
    </div>
  );
}
