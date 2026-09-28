import { useState } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg } from "../../lib/api";
import { useApi, qs } from "../../lib/hooks";
import { formatRp, formatDate, todayISO } from "../../lib/format";
import { PageHeader, DataTable, Modal, ConfirmDialog, Field, TextInput, NumberInput, SelectInput, TextArea, SummaryRow, PeriodFilter, usePeriod, StatCard } from "../../components/common";
import { Button } from "../../components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../../components/ui/tabs";
import { channelOpts, StatusBadge, ChannelBadge } from "../../lib/marketplace";

const EMPTY = { channel: "Shopee", settlement_id: "", settlement_date: todayISO(), order_id: "", gross_sales: 0, discount: 0, voucher: 0, marketplace_fee: 0, shipping_fee: 0, advertising_fee: 0, refund: 0, other_deduction: 0, actual_payout: 0, payment_account_id: "", notes: "" };
const NUMS = [["gross_sales", "Gross Sales"], ["discount", "Discount"], ["voucher", "Voucher"], ["marketplace_fee", "Marketplace Fee"], ["shipping_fee", "Shipping Fee"], ["advertising_fee", "Advertising Fee"], ["refund", "Refund"], ["other_deduction", "Other Deduction"]];
const n = (v) => parseFloat(v) || 0;
const RECON_STATUS = ["Matched", "Difference", "Pending", "Refunded"].map((s) => ({ value: s, label: s }));

function SettlementForm({ form, setForm, accounts }) {
  const set = (k) => (v) => setForm({ ...form, [k]: v?.target ? v.target.value : v });
  const expected = n(form.gross_sales) - NUMS.slice(1).reduce((a, [k]) => a + n(form[k]), 0);
  const fillFromOrder = async () => {
    if (!form.order_id) return;
    try {
      const { data } = await api.get(`/marketplace/orders${qs({ q: form.order_id, start: "", end: "" })}`);
      const os = data.filter((o) => o.order_id === form.order_id.trim() && o.channel === form.channel);
      if (!os.length) return toast.error("Order tidak ditemukan untuk channel ini");
      const s = (k) => os.reduce((a, o) => a + (o[k] || 0), 0);
      setForm({ ...form, gross_sales: s("gross_revenue"), discount: s("discount"), voucher: s("voucher"), marketplace_fee: s("marketplace_fee_total"), advertising_fee: s("ad_fee"), refund: s("refund") });
      toast.success(`Diisi dari ${os.length} baris order`);
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <Field label="Channel" required><SelectInput value={form.channel} onChange={set("channel")} options={channelOpts} allowEmpty={false} data-testid="settlement-channel" /></Field>
      <Field label="Settlement ID" required><TextInput value={form.settlement_id} onChange={set("settlement_id")} data-testid="settlement-id" /></Field>
      <Field label="Settlement Date" required><TextInput type="date" value={form.settlement_date} onChange={set("settlement_date")} data-testid="settlement-date" /></Field>
      <Field label="Order ID" required className="sm:col-span-2"><div className="flex gap-2"><TextInput value={form.order_id} onChange={set("order_id")} data-testid="settlement-order-id" /><Button type="button" variant="outline" onClick={fillFromOrder} data-testid="settlement-fill-btn">Isi dari order</Button></div></Field>
      <Field label="Payment Account"><SelectInput value={form.payment_account_id} onChange={set("payment_account_id")} options={(accounts || []).map((a) => ({ value: a.id, label: a.name }))} placeholder="Tanpa posting kas" data-testid="settlement-account" /></Field>
      {NUMS.map(([k, l]) => <Field key={k} label={l}><NumberInput value={form[k]} onChange={set(k)} data-testid={`settlement-${k}`} /></Field>)}
      <Field label="Actual Payout (uang diterima)" required><NumberInput value={form.actual_payout} onChange={set("actual_payout")} data-testid="settlement-actual" /></Field>
      <Field label="Notes" className="sm:col-span-2"><TextArea value={form.notes} onChange={set("notes")} data-testid="settlement-notes" /></Field>
      <div className="sm:col-span-3 rounded-lg border bg-muted/30 p-3">
        <SummaryRow label="Expected Payout" value={formatRp(expected)} bold testId="settlement-expected" />
        <SummaryRow label="Difference (actual − expected)" value={formatRp(n(form.actual_payout) - expected)} tone={Math.abs(n(form.actual_payout) - expected) < 1 ? "good" : "bad"} testId="settlement-diff" />
        <p className="mt-1 text-xs text-muted-foreground">Payout = uang yang benar-benar diterima dari marketplace. Ini <b>bukan</b> profit. Bila akun kas dipilih, actual payout dicatat sebagai kas masuk.</p>
      </div>
    </div>
  );
}

function Settlements({ period, channel }) {
  const { data, loading, reload } = useApi(`/marketplace/settlements${qs({ start: period.range.start, end: period.range.end, channel })}`);
  const { data: accounts } = useApi("/cash/accounts");
  const [form, setForm] = useState(null);
  const [del, setDel] = useState(null);
  const save = async () => {
    try {
      const payload = { ...form, payment_account_id: form.payment_account_id || null, ...Object.fromEntries([...NUMS.map(([k]) => k), "actual_payout"].map((k) => [k, n(form[k])])) };
      if (form.id) await api.put(`/marketplace/settlements/${form.id}`, payload); else await api.post("/marketplace/settlements", payload);
      toast.success("Settlement tersimpan"); setForm(null); reload();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const remove = async () => { try { await api.delete(`/marketplace/settlements/${del.id}`); toast.success("Dihapus"); setDel(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setForm({ ...EMPTY, channel: channel || "Shopee" })} data-testid="settlement-add-btn"><Plus className="mr-1 h-4 w-4" />Settlement</Button></div>
      <DataTable loading={loading} rows={data || []} filename="Settlement Payout" testId="settlements-table" columns={[
        { key: "settlement_date", label: "Tanggal", render: (r) => formatDate(r.settlement_date) }, { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> }, { key: "settlement_id", label: "Settlement ID" }, { key: "order_id", label: "Order ID" },
        { key: "gross_sales", label: "Gross Sales", align: "right", render: (r) => formatRp(r.gross_sales) }, { key: "marketplace_fee", label: "MP Fee", align: "right", render: (r) => formatRp(r.marketplace_fee) }, { key: "refund", label: "Refund", align: "right", render: (r) => formatRp(r.refund) },
        { key: "expected_payout", label: "Expected Payout", align: "right", render: (r) => formatRp(r.expected_payout) }, { key: "actual_payout", label: "Actual Payout", align: "right", render: (r) => formatRp(r.actual_payout) },
        { key: "difference", label: "Selisih", align: "right", render: (r) => <span className={Math.abs(r.difference) >= 1 ? "text-red-600" : ""}>{formatRp(r.difference)}</span> }, { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> }, { key: "payment_account_name", label: "Akun" },
        { label: "Aksi", noExport: true, align: "right", render: (r) => <div className="flex justify-end gap-1"><Button variant="ghost" size="sm" onClick={() => setForm({ ...EMPTY, ...r, payment_account_id: r.payment_account_id || "" })} data-testid="settlement-edit-btn"><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" className="text-red-600" onClick={() => setDel(r)} data-testid="settlement-delete-btn"><Trash2 className="h-4 w-4" /></Button></div> },
      ]} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? "Edit Settlement" : "Tambah Settlement / Payout"} wide footer={<><Button variant="outline" onClick={() => setForm(null)}>Batal</Button><Button onClick={save} data-testid="settlement-save-btn">Simpan</Button></>}>
        {form && <SettlementForm form={form} setForm={setForm} accounts={accounts} />}
      </Modal>
      <ConfirmDialog open={!!del} onClose={() => setDel(null)} onConfirm={remove} title={`Hapus settlement ${del?.settlement_id}?`} description="Kas masuk yang terkait juga dihapus." />
    </div>
  );
}

function Reconciliation({ period, channel }) {
  const [status, setStatus] = useState("");
  const { data, loading } = useApi(`/marketplace/reconciliation${qs({ start: period.range.start, end: period.range.end, channel, status })}`);
  const s = data?.summary;
  return (
    <div className="space-y-4" data-testid="reconciliation-panel">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Total Penjualan" value={formatRp(s?.total_sales)} testId="recon-kpi-sales" /><StatCard label="Total Potongan" value={formatRp(s?.total_deductions)} tone="accent" testId="recon-kpi-deductions" /><StatCard label="Expected Payout" value={formatRp(s?.expected_payout)} tone="primary" testId="recon-kpi-expected" /><StatCard label="Actual Payout" value={formatRp(s?.actual_payout)} tone="good" testId="recon-kpi-actual" /><StatCard label="Selisih" value={formatRp(s?.difference)} tone={Math.abs(s?.difference || 0) >= 1 ? "bad" : "good"} sub={s ? `Matched ${s.counts.Matched} · Difference ${s.counts.Difference} · Pending ${s.counts.Pending} · Refunded ${s.counts.Refunded}` : ""} testId="recon-kpi-diff" />
      </div>
      <DataTable loading={loading} rows={data?.rows || []} filename="Rekonsiliasi Marketplace" testId="reconciliation-table" toolbar={<SelectInput className="h-8 w-auto text-xs" value={status} onChange={setStatus} options={RECON_STATUS} placeholder="Semua status" data-testid="recon-filter-status" />} columns={[
        { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> }, { key: "order_id", label: "Order ID" }, { key: "products", label: "Produk" }, { key: "order_status", label: "Status Order", render: (r) => <StatusBadge status={r.order_status} /> },
        { key: "total_sales", label: "Total Penjualan", align: "right", render: (r) => formatRp(r.total_sales) }, { key: "total_deductions", label: "Total Potongan", align: "right", render: (r) => formatRp(r.total_deductions) }, { key: "expected_payout", label: "Expected Payout", align: "right", render: (r) => formatRp(r.expected_payout) },
        { key: "actual_payout", label: "Actual Payout", align: "right", render: (r) => formatRp(r.actual_payout) }, { key: "difference", label: "Selisih", align: "right", render: (r) => <span className={Math.abs(r.difference) >= 1 ? "text-red-600 font-medium" : ""}>{formatRp(r.difference)}</span> },
        { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> }, { key: "settlement_ids", label: "Settlement", render: (r) => r.settlement_ids.join(", ") || "-", export: (r) => r.settlement_ids.join(", ") },
      ]} />
    </div>
  );
}

export default function SettlementsPage() {
  const period = usePeriod("month");
  const [channel, setChannel] = useState("");
  return (
    <div data-testid="settlements-page">
      <PageHeader title="Settlement & Rekonsiliasi Marketplace" subtitle="Payout = uang yang diterima dari marketplace (bukan profit). Rekonsiliasi membandingkan expected payout dari order dengan actual payout settlement." />
      <div className="mb-4 flex flex-wrap items-center gap-2"><PeriodFilter period={period} /><SelectInput className="h-8 w-auto text-xs" value={channel} onChange={setChannel} options={channelOpts} placeholder="Semua channel" data-testid="settlement-filter-channel" /></div>
      <Tabs defaultValue="settlement">
        <TabsList><TabsTrigger value="settlement" data-testid="tab-settlement">Settlement / Payout</TabsTrigger><TabsTrigger value="recon" data-testid="tab-reconciliation">Rekonsiliasi</TabsTrigger></TabsList>
        <TabsContent value="settlement" className="mt-4"><Settlements period={period} channel={channel} /></TabsContent>
        <TabsContent value="recon" className="mt-4"><Reconciliation period={period} channel={channel} /></TabsContent>
      </Tabs>
    </div>
  );
}
