import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, Eye, AlertTriangle } from "lucide-react";
import { api, errMsg } from "../../lib/api";
import { useApi, qs } from "../../lib/hooks";
import { formatRp, formatNum, formatPct, formatDate, todayISO } from "../../lib/format";
import { PageHeader, DataTable, Modal, ConfirmDialog, Field, TextInput, NumberInput, SelectInput, TextArea, SummaryRow, PeriodFilter, usePeriod, StatCard } from "../../components/common";
import { Button } from "../../components/ui/button";
import { channelOpts, statusOpts, StatusBadge, ChannelBadge, useProducts, productOpts, STATUSES } from "../../lib/marketplace";

const EMPTY = { order_id: "", date: todayISO(), channel: "Shopee", customer: "", product_id: "", qty: 1, normal_price: "", selling_price: "", discount: 0, voucher: 0, shipping_fee: 0, shipping_subsidy: 0, fee_mode: "auto", admin_fee: "", service_fee: "", transaction_fee: "", other_marketplace_fee: "", ad_fee: 0, other_operational_fee: 0, refund: 0, pack_mode: "auto", packaging_cost_per_unit: "", status: "Selesai", notes: "" };
const n = (v) => (v === "" || v === null || v === undefined ? 0 : parseFloat(v) || 0);

export const toPayload = (f) => ({
  ...f, qty: n(f.qty), selling_price: n(f.selling_price), normal_price: f.normal_price === "" ? null : n(f.normal_price), discount: n(f.discount), voucher: n(f.voucher), shipping_fee: n(f.shipping_fee), shipping_subsidy: n(f.shipping_subsidy),
  admin_fee: f.fee_mode === "auto" ? null : n(f.admin_fee), service_fee: f.fee_mode === "auto" ? null : n(f.service_fee), transaction_fee: f.fee_mode === "auto" ? null : n(f.transaction_fee), other_marketplace_fee: f.fee_mode === "auto" ? null : n(f.other_marketplace_fee),
  ad_fee: n(f.ad_fee), other_operational_fee: n(f.other_operational_fee), refund: n(f.refund), packaging_cost_per_unit: f.pack_mode === "auto" ? null : n(f.packaging_cost_per_unit),
});

export function OrderBreakdown({ o, testId = "order-breakdown" }) {
  if (!o) return null;
  return (
    <div className="rounded-lg border bg-muted/30 p-3" data-testid={testId}>
      <SummaryRow label={`Omzet Kotor (${formatRp(o.selling_price)} × ${formatNum(o.qty)})`} value={formatRp(o.gross_revenue)} testId={`${testId}-gross`} />
      <SummaryRow label="− Diskon − Voucher − Refund" value={formatRp(-(o.discount + o.voucher + o.refund))} />
      <SummaryRow label="Omzet Bersih" value={formatRp(o.net_revenue)} bold testId={`${testId}-net`} />
      <SummaryRow label={`− HPP Produk (${formatRp(o.hpp_unit, true)}/unit)`} value={formatRp(-o.hpp_total)} testId={`${testId}-hpp`} />
      <SummaryRow label={`− Biaya Beban Packaging (${formatRp(o.packaging_cost_per_unit, true)}/unit${o.packaging_name && o.packaging_name !== "manual" ? ` · ${o.packaging_name}` : ""})`} value={formatRp(-o.packaging_cost)} testId={`${testId}-packaging`} />
      <SummaryRow label="Gross Profit" value={formatRp(o.gross_profit)} bold tone={o.gross_profit >= 0 ? "good" : "bad"} testId={`${testId}-gross-profit`} />
      <SummaryRow label={`− Biaya Marketplace (${o.fee_source === "auto" ? "otomatis dari pengaturan" : "manual"})`} value={formatRp(-o.marketplace_fee_total)} testId={`${testId}-fees`} />
      {o.fee_detail?.map((d) => <p key={d.fee_id} className="pl-4 text-xs text-muted-foreground num">{d.name}: {formatRp(d.amount)}</p>)}
      <SummaryRow label="− Biaya Iklan" value={formatRp(-o.ad_fee)} />
      {o.other_operational_fee > 0 && <SummaryRow label="− Biaya Operasional Lain" value={formatRp(-o.other_operational_fee)} />}
      <SummaryRow label="Net Profit" value={formatRp(o.net_profit)} bold tone={o.net_profit >= 0 ? "good" : "bad"} testId={`${testId}-net-profit`} />
      <SummaryRow label="Margin" value={formatPct(o.margin_pct)} testId={`${testId}-margin`} />
      <div className="mt-2 grid grid-cols-2 gap-2 border-t pt-2 text-xs text-muted-foreground">
        <span>Total dibayar customer: <b className="num text-foreground">{formatRp(o.customer_paid)}</b></span>
        <span>Total diterima seller (expected payout): <b className="num text-foreground">{formatRp(o.seller_received)}</b></span>
      </div>
      {o.stock_warning && <p className="mt-2 flex items-center gap-1 text-xs text-orange-600" data-testid={`${testId}-stock-warning`}><AlertTriangle className="h-3 w-3" />{o.stock_warning}</p>}
    </div>
  );
}

function OrderForm({ form, setForm, products }) {
  const [preview, setPreview] = useState(null);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v?.target ? v.target.value : v }));
  useEffect(() => {
    if (!form.product_id || !form.order_id) { setPreview(null); return; }
    const t = setTimeout(() => api.post("/marketplace/orders/preview", toPayload(form)).then((r) => setPreview(r.data)).catch(() => setPreview(null)), 350);
    return () => clearTimeout(t);
  }, [form]);
  const pickProduct = (pid) => { const p = (products || []).find((x) => x.id === pid); setForm((f) => ({ ...f, product_id: pid, selling_price: f.selling_price || p?.selling_price || "", normal_price: f.normal_price || p?.selling_price || "" })); };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Order ID / No. Pesanan" required><TextInput value={form.order_id} onChange={set("order_id")} data-testid="order-order-id" /></Field>
        <Field label="Tanggal Pesanan" required><TextInput type="date" value={form.date} onChange={set("date")} data-testid="order-date" /></Field>
        <Field label="Channel" required><SelectInput value={form.channel} onChange={set("channel")} options={channelOpts} allowEmpty={false} data-testid="order-channel" /></Field>
        <Field label="Produk / SKU" required className="sm:col-span-2"><SelectInput value={form.product_id} onChange={pickProduct} options={productOpts(products)} data-testid="order-product" /></Field>
        <Field label="Customer"><TextInput value={form.customer} onChange={set("customer")} data-testid="order-customer" /></Field>
        <Field label="Qty" required><NumberInput value={form.qty} onChange={set("qty")} data-testid="order-qty" /></Field>
        <Field label="Harga Normal"><NumberInput value={form.normal_price} onChange={set("normal_price")} data-testid="order-normal-price" /></Field>
        <Field label="Harga Jual" required><NumberInput value={form.selling_price} onChange={set("selling_price")} data-testid="order-selling-price" /></Field>
        <Field label="Diskon"><NumberInput value={form.discount} onChange={set("discount")} data-testid="order-discount" /></Field>
        <Field label="Voucher"><NumberInput value={form.voucher} onChange={set("voucher")} data-testid="order-voucher" /></Field>
        <Field label="Refund / Retur"><NumberInput value={form.refund} onChange={set("refund")} data-testid="order-refund" /></Field>
        <Field label="Ongkir (dibayar customer)"><NumberInput value={form.shipping_fee} onChange={set("shipping_fee")} data-testid="order-shipping" /></Field>
        <Field label="Subsidi Ongkir"><NumberInput value={form.shipping_subsidy} onChange={set("shipping_subsidy")} data-testid="order-shipping-subsidy" /></Field>
        <Field label="Status Pesanan" required><SelectInput value={form.status} onChange={set("status")} options={statusOpts} allowEmpty={false} data-testid="order-status" /></Field>
        <div className="sm:col-span-3 rounded-lg border p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-medium">Biaya Marketplace</span>
            <SelectInput className="h-8 w-auto text-xs" value={form.fee_mode} onChange={set("fee_mode")} allowEmpty={false} options={[{ value: "auto", label: "Otomatis dari Pengaturan Biaya Channel" }, { value: "manual", label: "Isi manual" }]} data-testid="order-fee-mode" /></div>
          {form.fee_mode === "manual" && <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Biaya Admin"><NumberInput value={form.admin_fee} onChange={set("admin_fee")} data-testid="order-admin-fee" /></Field>
            <Field label="Biaya Layanan"><NumberInput value={form.service_fee} onChange={set("service_fee")} data-testid="order-service-fee" /></Field>
            <Field label="Biaya Transaksi"><NumberInput value={form.transaction_fee} onChange={set("transaction_fee")} data-testid="order-transaction-fee" /></Field>
            <Field label="Biaya MP Lainnya"><NumberInput value={form.other_marketplace_fee} onChange={set("other_marketplace_fee")} data-testid="order-other-mp-fee" /></Field>
          </div>}
        </div>
        <Field label="Biaya Iklan"><NumberInput value={form.ad_fee} onChange={set("ad_fee")} data-testid="order-ad-fee" /></Field>
        <Field label="Biaya Operasional Lain"><NumberInput value={form.other_operational_fee} onChange={set("other_operational_fee")} data-testid="order-other-op-fee" /></Field>
        <Field label="Biaya Packaging / Unit">
          <div className="flex gap-2">
            <SelectInput className="w-auto" value={form.pack_mode} onChange={set("pack_mode")} allowEmpty={false} options={[{ value: "auto", label: "Dari produk" }, { value: "manual", label: "Manual" }]} data-testid="order-pack-mode" />
            {form.pack_mode === "manual" && <NumberInput value={form.packaging_cost_per_unit} onChange={set("packaging_cost_per_unit")} data-testid="order-packaging-unit" />}
          </div>
        </Field>
        <Field label="Keterangan" className="sm:col-span-3"><TextArea value={form.notes} onChange={set("notes")} data-testid="order-notes" /></Field>
      </div>
      <div>
        <p className="mb-2 text-sm font-medium">Ringkasan Perhitungan</p>
        {preview ? <OrderBreakdown o={preview} testId="order-preview" /> : <p className="text-sm text-muted-foreground">Isi Order ID dan pilih produk untuk melihat perhitungan.</p>}
      </div>
    </div>
  );
}

export default function Orders() {
  const period = usePeriod("month");
  const [filter, setFilter] = useState({ channel: "", status: "", product_id: "", q: "" });
  const url = `/marketplace/orders${qs({ start: period.range.start, end: period.range.end, ...filter })}`;
  const { data, loading, reload } = useApi(url);
  const { data: products } = useProducts();
  const [form, setForm] = useState(null);
  const [del, setDel] = useState(null);
  const [detail, setDetail] = useState(null);
  const [saving, setSaving] = useState(false);
  const rows = useMemo(() => data || [], [data]);
  const sum = useMemo(() => { const a = rows.filter((o) => !["Pending", "Dibatalkan"].includes(o.status)); return { net: a.reduce((s, o) => s + o.net_revenue, 0), profit: a.reduce((s, o) => s + o.net_profit, 0), pack: a.reduce((s, o) => s + o.packaging_cost, 0), fee: a.reduce((s, o) => s + o.marketplace_fee_total, 0) }; }, [rows]);
  const save = async () => {
    try {
      setSaving(true);
      const r = form.id ? await api.put(`/marketplace/orders/${form.id}`, toPayload(form)) : await api.post("/marketplace/orders", toPayload(form));
      toast.success("Order tersimpan"); if (r.data.stock_warning) toast.warning(r.data.stock_warning);
      setForm(null); reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  const edit = (o) => setForm({ ...EMPTY, ...o, fee_mode: o.fee_source === "auto" ? "auto" : "manual", pack_mode: o.packaging_name === "manual" ? "manual" : "auto", normal_price: o.normal_price ?? "" });
  const setStatus = async (o, status) => { try { const r = await api.patch(`/marketplace/orders/${o.id}/status`, { status }); toast.success(`Status → ${status}`); if (r.data.stock_warning) toast.warning(r.data.stock_warning); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const remove = async () => { try { await api.delete(`/marketplace/orders/${del.id}`); toast.success("Order dihapus"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const columns = [
    { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "order_id", label: "Order ID", className: "font-medium" }, { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> },
    { key: "product_name", label: "Produk" }, { key: "sku", label: "SKU" }, { key: "qty", label: "Qty", align: "right", render: (r) => formatNum(r.qty) }, { key: "customer", label: "Customer" },
    { key: "gross_revenue", label: "Omzet Kotor", align: "right", render: (r) => formatRp(r.gross_revenue) }, { key: "net_revenue", label: "Omzet Bersih", align: "right", render: (r) => formatRp(r.net_revenue) },
    { key: "hpp_total", label: "HPP", align: "right", render: (r) => formatRp(r.hpp_total) }, { key: "packaging_cost", label: "Packaging", align: "right", render: (r) => formatRp(r.packaging_cost) },
    { key: "marketplace_fee_total", label: "Biaya MP", align: "right", render: (r) => formatRp(r.marketplace_fee_total) }, { key: "ad_fee", label: "Iklan", align: "right", render: (r) => formatRp(r.ad_fee) },
    { key: "net_profit", label: "Net Profit", align: "right", render: (r) => <span className={r.net_profit < 0 ? "text-red-600" : "text-emerald-700"}>{formatRp(r.net_profit)}</span> }, { key: "margin_pct", label: "Margin %", align: "right", render: (r) => formatPct(r.margin_pct) },
    { key: "status", label: "Status", render: (r) => <SelectInput className="h-8 w-auto text-xs" value={r.status} onChange={(v) => setStatus(r, v)} options={statusOpts} allowEmpty={false} data-testid={`order-status-select-${r.order_id}`} />, export: (r) => r.status },
    { label: "Aksi", noExport: true, align: "right", render: (r) => <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => setDetail(r)} data-testid="order-detail-btn"><Eye className="h-4 w-4" /></Button><Button variant="ghost" size="sm" onClick={() => edit(r)} data-testid="order-edit-btn"><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="order-delete-btn"><Trash2 className="h-4 w-4" /></Button></div> },
  ];
  return (
    <div data-testid="marketplace-orders-page">
      <PageHeader title="Penjualan Marketplace & Website" subtitle="Order per channel dengan HPP, Biaya Beban Packaging, biaya marketplace, iklan, dan profit terpisah." actions={<Button onClick={() => setForm({ ...EMPTY })} data-testid="order-add-btn"><Plus className="mr-1 h-4 w-4" />Order Manual</Button>} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Omzet Bersih" value={formatRp(sum.net)} tone="primary" testId="orders-kpi-net" /><StatCard label="Biaya Packaging" value={formatRp(sum.pack)} testId="orders-kpi-pack" /><StatCard label="Biaya Marketplace" value={formatRp(sum.fee)} tone="accent" testId="orders-kpi-fee" /><StatCard label="Net Profit" value={formatRp(sum.profit)} tone={sum.profit >= 0 ? "good" : "bad"} testId="orders-kpi-profit" />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <PeriodFilter period={period} />
        <SelectInput className="h-8 w-auto text-xs" value={filter.channel} onChange={(v) => setFilter({ ...filter, channel: v })} options={channelOpts} placeholder="Semua channel" data-testid="orders-filter-channel" />
        <SelectInput className="h-8 w-auto text-xs" value={filter.status} onChange={(v) => setFilter({ ...filter, status: v })} options={statusOpts} placeholder="Semua status" data-testid="orders-filter-status" />
        <SelectInput className="h-8 w-auto max-w-[220px] text-xs" value={filter.product_id} onChange={(v) => setFilter({ ...filter, product_id: v })} options={productOpts(products)} placeholder="Semua produk" data-testid="orders-filter-product" />
      </div>
      <DataTable columns={columns} rows={rows} loading={loading} filename="Penjualan Marketplace" testId="orders-table" searchKeys={["order_id", "customer", "product_name", "sku", "channel", "status"]} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? `Edit Order ${form.order_id}` : "Order Manual"} wide footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} disabled={saving || !form?.order_id || !form?.product_id} data-testid="order-save-btn">Simpan</Button></>}>
        {form && <OrderForm form={form} setForm={setForm} products={products} />}
      </Modal>
      <Modal open={!!detail} onClose={() => setDetail(null)} title={`Order ${detail?.order_id}`} description={detail ? `${detail.channel} · ${formatDate(detail.date)} · ${detail.product_name} ×${formatNum(detail.qty)} · ${detail.customer || "-"}` : ""}>
        {detail && <><div className="flex items-center gap-2"><StatusBadge status={detail.status} />{detail.stock_deducted ? <span className="badge-ok">Stok sudah dikurangi</span> : <span className="badge-muted">Stok belum dikurangi</span>}<span className="text-xs text-muted-foreground">sumber: {detail.source}</span></div><OrderBreakdown o={detail} testId="order-detail-breakdown" /></>}
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Hapus order ${del?.order_id}?`} description="Stok yang sudah dikurangi akan dikembalikan." />
    </div>
  );
}

export { STATUSES };
