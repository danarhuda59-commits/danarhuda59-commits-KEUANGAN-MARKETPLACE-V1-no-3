import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, ArrowLeftRight } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, LineChart, Line } from "recharts";
import { api, errMsg } from "../lib/api";
import { useApi, qs } from "../lib/hooks";
import { formatRp, formatNum, formatPct, formatDate, todayISO } from "../lib/format";
import { PageHeader, DataTable, Modal, Field, TextInput, NumberInput, SelectInput, SummaryRow, PeriodFilter, usePeriod, StatCard, ExportButtons } from "../components/common";
import { Button } from "../components/ui/button";

const ACC_TYPES = [{ value: "cash", label: "Kas" }, { value: "bank", label: "Bank" }, { value: "ewallet", label: "E-Wallet" }, { value: "marketplace", label: "Saldo Marketplace" }];
const CAT = { sale: "Penjualan", purchase: "Pembelian", expense: "Pengeluaran", transfer: "Transfer", capital: "Modal", other: "Lainnya", opening: "Saldo awal" };

export function Cash() {
  const period = usePeriod("month");
  const [accId, setAccId] = useState("");
  const accounts = useApi("/cash/accounts");
  const txs = useApi(`/cash/transactions${qs({ ...period.range, account_id: accId })}`, [period.range.start, period.range.end, accId]);
  const [accForm, setAccForm] = useState(null);
  const [txForm, setTxForm] = useState(null);
  const accs = accounts.data || [];
  const rows = txs.data || [];
  const totIn = rows.filter((t) => t.direction === "in").reduce((a, t) => a + t.amount, 0);
  const totOut = rows.filter((t) => t.direction === "out").reduce((a, t) => a + t.amount, 0);
  const saveAcc = async () => {
    try { if (accForm.id) await api.put(`/cash/accounts/${accForm.id}`, { ...accForm, opening_balance: parseFloat(accForm.opening_balance || 0) }); else await api.post("/cash/accounts", { ...accForm, opening_balance: parseFloat(accForm.opening_balance || 0) }); toast.success("Akun tersimpan"); setAccForm(null); accounts.reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const saveTx = async () => {
    if (!(parseFloat(txForm.amount) > 0)) return toast.error("Nominal harus lebih dari 0");
    try { await api.post("/cash/transactions", { ...txForm, amount: parseFloat(txForm.amount) }); toast.success("Transaksi kas tersimpan"); setTxForm(null); txs.reload(); accounts.reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="cash-page">
      <PageHeader title="Kas & Rekening" subtitle="Saldo Akhir = Saldo Awal + Pemasukan − Pengeluaran" actions={<><Button variant="outline" onClick={() => setAccForm({ name: "", type: "cash", opening_balance: 0 })} data-testid="account-add-btn"><Plus className="mr-1 h-4 w-4" />Akun</Button><Button onClick={() => setTxForm({ account_id: accs[0]?.id || "", direction: "in", amount: "", date: todayISO(), category: "other", description: "", to_account_id: "" })} data-testid="cashtx-add-btn"><Plus className="mr-1 h-4 w-4" />Transaksi Manual</Button></>} />
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <button onClick={() => setAccId("")} className={`stat-card text-left ${accId === "" ? "ring-2 ring-primary" : ""}`} data-testid="account-card-all"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Semua Akun</p><p className="mt-2 text-xl font-bold num">{formatRp(accs.reduce((a, x) => a + x.balance, 0))}</p></button>
        {accs.map((a) => (
          <button key={a.id} onClick={() => setAccId(a.id)} className={`stat-card text-left ${accId === a.id ? "ring-2 ring-primary" : ""}`} data-testid="account-card">
            <div className="flex justify-between"><p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{a.name}</p><span className="badge-muted">{ACC_TYPES.find((t) => t.value === a.type)?.label}</span></div>
            <p className="mt-2 text-xl font-bold num">{formatRp(a.balance)}</p><p className="text-xs text-muted-foreground">Saldo awal {formatRp(a.opening_balance)} · <span className="underline" onClick={(e) => { e.stopPropagation(); setAccForm(a); }}>edit</span></p>
          </button>))}
      </div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><PeriodFilter period={period} /></div>
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Saldo awal periode" value={formatRp((accId ? accs.filter((a) => a.id === accId) : accs).reduce((a, x) => a + x.balance, 0) - totIn + totOut)} testId="cash-opening" />
        <StatCard label="Pemasukan" value={formatRp(totIn)} tone="good" testId="cash-in" /><StatCard label="Pengeluaran" value={formatRp(totOut)} tone="bad" testId="cash-out" />
        <StatCard label="Saldo akhir" value={formatRp((accId ? accs.filter((a) => a.id === accId) : accs).reduce((a, x) => a + x.balance, 0))} tone="primary" testId="cash-closing" />
      </div>
      <DataTable testId="cash-table" filename="kas" rows={rows} loading={txs.loading} searchKeys={["description", "account_name", "category"]} columns={[
        { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "account_name", label: "Akun" }, { key: "category", label: "Kategori", render: (r) => CAT[r.category] || r.category }, { key: "description", label: "Deskripsi" },
        { label: "Masuk", align: "right", key: (r) => (r.direction === "in" ? r.amount : ""), render: (r) => (r.direction === "in" ? <span className="text-emerald-700">{formatRp(r.amount)}</span> : "") }, { label: "Keluar", align: "right", key: (r) => (r.direction === "out" ? r.amount : ""), render: (r) => (r.direction === "out" ? <span className="text-red-600">{formatRp(r.amount)}</span> : "") },
        { label: "", noExport: true, align: "right", render: (r) => (["manual", "transfer"].includes(r.ref_type) ? <Button variant="ghost" size="sm" className="text-red-600" onClick={async () => { try { await api.delete(`/cash/transactions/${r.id}`); txs.reload(); accounts.reload(); } catch (e) { toast.error(errMsg(e)); } }} data-testid="cashtx-delete-btn"><Trash2 className="h-4 w-4" /></Button> : null) },
      ]} />
      <Modal open={!!accForm} onClose={() => setAccForm(null)} title={accForm?.id ? "Edit Akun" : "Tambah Akun Kas/Bank"} footer={<><Button variant="outline" onClick={() => setAccForm(null)}>Batal</Button><Button onClick={saveAcc} data-testid="account-save-btn">Simpan</Button></>}>
        {accForm && <div className="grid gap-4 sm:grid-cols-2"><Field label="Nama Akun" required><TextInput value={accForm.name} onChange={(e) => setAccForm({ ...accForm, name: e.target.value })} data-testid="account-name-input" /></Field><Field label="Tipe"><SelectInput value={accForm.type} onChange={(v) => setAccForm({ ...accForm, type: v })} allowEmpty={false} options={ACC_TYPES} data-testid="account-type-select" /></Field><Field label="Saldo Awal"><NumberInput value={accForm.opening_balance} onChange={(v) => setAccForm({ ...accForm, opening_balance: v })} data-testid="account-opening-input" /></Field></div>}
      </Modal>
      <Modal open={!!txForm} onClose={() => setTxForm(null)} title="Transaksi Kas Manual / Transfer" footer={<><Button variant="outline" onClick={() => setTxForm(null)}>Batal</Button><Button onClick={saveTx} data-testid="cashtx-save-btn">Simpan</Button></>}>
        {txForm && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Jenis"><SelectInput value={txForm.direction} onChange={(v) => setTxForm({ ...txForm, direction: v })} allowEmpty={false} options={[{ value: "in", label: "Pemasukan" }, { value: "out", label: "Pengeluaran" }, { value: "transfer", label: "Transfer antar akun" }]} data-testid="cashtx-direction-select" /></Field>
          <Field label="Tanggal"><TextInput type="date" value={txForm.date} onChange={(e) => setTxForm({ ...txForm, date: e.target.value })} /></Field>
          <Field label={txForm.direction === "transfer" ? "Dari akun" : "Akun"}><SelectInput value={txForm.account_id} onChange={(v) => setTxForm({ ...txForm, account_id: v })} options={accs.map((a) => ({ value: a.id, label: a.name }))} data-testid="cashtx-account-select" /></Field>
          {txForm.direction === "transfer" ? <Field label="Ke akun"><SelectInput value={txForm.to_account_id} onChange={(v) => setTxForm({ ...txForm, to_account_id: v })} options={accs.map((a) => ({ value: a.id, label: a.name }))} data-testid="cashtx-to-account-select" /></Field>
            : <Field label="Kategori"><SelectInput value={txForm.category} onChange={(v) => setTxForm({ ...txForm, category: v })} allowEmpty={false} options={[{ value: "capital", label: "Modal / Setoran" }, { value: "other", label: "Lainnya" }, { value: "opening", label: "Saldo awal" }]} data-testid="cashtx-category-select" /></Field>}
          <Field label="Nominal" required><NumberInput value={txForm.amount} onChange={(v) => setTxForm({ ...txForm, amount: v })} data-testid="cashtx-amount-input" /></Field>
          <Field label="Deskripsi"><TextInput value={txForm.description} onChange={(e) => setTxForm({ ...txForm, description: e.target.value })} data-testid="cashtx-description-input" /></Field>
        </div>}
      </Modal>
    </div>
  );
}

export function ProfitLoss() {
  const period = usePeriod("month");
  const { data: d } = useApi(`/reports/profit-loss${qs(period.range)}`, [period.range.start, period.range.end]);
  const s = d?.summary || {};
  const prodCols = [{ key: "product_name", label: "Produk" }, { key: "qty", label: "Qty Terjual", align: "right", render: (r) => formatNum(r.qty) }, { key: "avg_price", label: "Harga Jual Rata2", align: "right", render: (r) => formatRp(r.avg_price) }, { key: "hpp_per_unit", label: "HPP/Unit", align: "right", render: (r) => formatRp(r.hpp_per_unit, true) }, { key: "omzet", label: "Omzet", align: "right", render: (r) => formatRp(r.omzet) }, { key: "hpp", label: "HPP", align: "right", render: (r) => formatRp(r.hpp) }, { key: "profit", label: "Laba", align: "right", render: (r) => formatRp(r.profit) }, { key: "margin_pct", label: "Margin", align: "right", render: (r) => formatPct(r.margin_pct) }];
  return (
    <div data-testid="pl-page">
      <PageHeader title="Laporan Laba Rugi" subtitle="Penjualan − HPP = Laba Kotor; Laba Kotor − Beban Operasional = Laba Bersih" actions={<PeriodFilter period={period} />} />
      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <div className="card-panel" data-testid="pl-statement">
          <h3 className="mb-3 font-heading font-semibold">Ikhtisar</h3>
          <SummaryRow label="Omzet (bruto)" value={formatRp(s.omzet)} testId="pl-omzet" /><SummaryRow label="Biaya platform/layanan" value={`- ${formatRp(s.sales_fees)}`} /><SummaryRow label="PENJUALAN BERSIH" value={formatRp(s.net_sales)} bold />
          <SummaryRow label="HPP Penjualan" value={`- ${formatRp(s.hpp)}`} testId="pl-hpp" /><SummaryRow label="LABA KOTOR" value={formatRp(s.gross_profit)} bold tone={s.gross_profit >= 0 ? "good" : "bad"} testId="pl-gross" /><SummaryRow label="Margin kotor" value={formatPct(s.gross_margin_pct)} />
          <SummaryRow label="Beban Operasional" value={`- ${formatRp(s.opex)}`} testId="pl-opex" /><SummaryRow label="LABA BERSIH" value={formatRp(s.net_profit)} bold tone={s.net_profit >= 0 ? "good" : "bad"} testId="pl-net" /><SummaryRow label="Margin bersih" value={formatPct(s.net_margin_pct)} />
          <h4 className="mt-4 mb-1 text-sm font-semibold">Rincian Beban Operasional</h4>
          {(d?.expenses_by_category || []).map((e) => <SummaryRow key={e.category} label={e.category} value={formatRp(e.amount)} />)}
          <div className="mt-3"><ExportButtons rows={[{ ...s }]} columns={Object.keys(s).map((k) => ({ key: k, label: k }))} filename="laba-rugi" /></div>
        </div>
        <div className="space-y-6">
          <div className="card-panel"><h3 className="mb-3 font-heading font-semibold">Tren Harian</h3>
            <ResponsiveContainer width="100%" height={240}><BarChart data={(d?.daily || []).map((x) => ({ ...x, label: formatDate(x.date).slice(0, 6) }))}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="label" fontSize={11} /><YAxis fontSize={11} width={56} tickFormatter={(v) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}jt` : `${Math.round(v / 1e3)}rb`)} /><Tooltip formatter={(v) => formatRp(v)} /><Legend /><Bar dataKey="omzet" name="Omzet" fill="#0F766E" /><Bar dataKey="hpp" name="HPP" fill="#F59E0B" /><Bar dataKey="expense" name="Beban" fill="#EA580C" /><Bar dataKey="profit" name="Laba" fill="#0284C7" /></BarChart></ResponsiveContainer></div>
          <div><h3 className="mb-3 font-heading font-semibold">Laba per Produk</h3><DataTable testId="pl-products" filename="laba-per-produk" rows={d?.by_product || []} columns={prodCols} /></div>
          <div><h3 className="mb-3 font-heading font-semibold">Laba per Channel</h3><DataTable testId="pl-channels" filename="laba-per-channel" rows={d?.by_channel || []} columns={[{ key: "channel", label: "Channel" }, { key: "count", label: "Transaksi", align: "right" }, { key: "omzet", label: "Omzet", align: "right", render: (r) => formatRp(r.omzet) }, { key: "fees", label: "Biaya", align: "right", render: (r) => formatRp(r.fees) }, { key: "net", label: "Bersih", align: "right", render: (r) => formatRp(r.net) }, { key: "hpp", label: "HPP", align: "right", render: (r) => formatRp(r.hpp) }, { key: "profit", label: "Laba", align: "right", render: (r) => formatRp(r.profit) }, { key: "margin_pct", label: "Margin", align: "right", render: (r) => formatPct(r.margin_pct) }]} /></div>
        </div>
      </div>
    </div>
  );
}

export function CashFlow() {
  const period = usePeriod("month");
  const [accId, setAccId] = useState("");
  const { data: accounts } = useApi("/cash/accounts");
  const { data: d } = useApi(`/reports/cash-flow${qs({ ...period.range, account_id: accId })}`, [period.range.start, period.range.end, accId]);
  return (
    <div data-testid="cashflow-page">
      <PageHeader title="Laporan Cash Flow" subtitle="Arus kas masuk & keluar per periode" actions={<><SelectInput value={accId} onChange={setAccId} options={(accounts || []).map((a) => ({ value: a.id, label: a.name }))} placeholder="Semua akun" className="w-44" data-testid="cashflow-account-select" /><PeriodFilter period={period} /></>} />
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"><StatCard label="Saldo Awal" value={formatRp(d?.opening_balance)} testId="cf-opening" /><StatCard label="Total Masuk" value={formatRp(d?.total_in)} tone="good" testId="cf-in" /><StatCard label="Total Keluar" value={formatRp(d?.total_out)} tone="bad" testId="cf-out" /><StatCard label="Saldo Akhir" value={formatRp(d?.closing_balance)} tone="primary" testId="cf-closing" /></div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card-panel"><h3 className="mb-3 font-heading font-semibold">Arus Masuk</h3>{(d?.inflow || []).map((x) => <SummaryRow key={x.category} label={CAT[x.category] || x.category} value={formatRp(x.amount)} tone="good" />)}{!(d?.inflow || []).length && <p className="text-sm text-muted-foreground">Tidak ada</p>}</div>
        <div className="card-panel"><h3 className="mb-3 font-heading font-semibold">Arus Keluar</h3>{(d?.outflow || []).map((x) => <SummaryRow key={x.category} label={CAT[x.category] || x.category} value={formatRp(x.amount)} tone="bad" />)}{!(d?.outflow || []).length && <p className="text-sm text-muted-foreground">Tidak ada</p>}</div>
        <div className="card-panel"><h3 className="mb-3 font-heading font-semibold">Saldo Harian</h3><ResponsiveContainer width="100%" height={200}><LineChart data={(d?.daily || []).map((x) => ({ ...x, label: formatDate(x.date).slice(0, 6) }))}><XAxis dataKey="label" fontSize={10} /><YAxis fontSize={10} width={56} tickFormatter={(v) => `${(v / 1e6).toFixed(1)}jt`} /><Tooltip formatter={(v) => formatRp(v)} /><Line type="monotone" dataKey="balance" name="Saldo" stroke="#0F766E" dot={false} /></LineChart></ResponsiveContainer></div>
      </div>
      <h3 className="mt-6 mb-3 font-heading font-semibold">Transaksi</h3>
      <DataTable testId="cashflow-table" filename="cash-flow" rows={d?.transactions || []} searchKeys={["description", "account_name"]} columns={[{ key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "account_name", label: "Akun" }, { key: "category", label: "Kategori", render: (r) => CAT[r.category] || r.category }, { key: "description", label: "Deskripsi" }, { label: "Masuk", align: "right", key: (r) => (r.direction === "in" ? r.amount : ""), render: (r) => (r.direction === "in" ? formatRp(r.amount) : "") }, { label: "Keluar", align: "right", key: (r) => (r.direction === "out" ? r.amount : ""), render: (r) => (r.direction === "out" ? formatRp(r.amount) : "") }]} />
    </div>
  );
}

export function Bep() {
  const { data: products } = useApi("/products");
  const saved = useApi("/bep");
  const [f, setF] = useState({ name: "", product_id: "", fixed_cost: "", selling_price: "", variable_cost: "" });
  const fixed = parseFloat(f.fixed_cost) || 0, price = parseFloat(f.selling_price) || 0, vc = parseFloat(f.variable_cost) || 0;
  const contrib = price - vc;
  const units = contrib > 0 ? fixed / contrib : null;
  const pick = (pid) => { const p = (products || []).find((x) => x.id === pid); setF({ ...f, product_id: pid, selling_price: p ? p.selling_price : f.selling_price, variable_cost: p ? p.avg_hpp : f.variable_cost, name: p ? `BEP ${p.name}` : f.name }); };
  const save = async () => {
    if (contrib <= 0) return toast.error("Harga jual harus lebih besar dari biaya variabel per unit");
    try { await api.post("/bep", { ...f, product_id: f.product_id || null, fixed_cost: fixed, selling_price: price, variable_cost: vc }); toast.success("Perhitungan BEP tersimpan"); saved.reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="bep-page">
      <PageHeader title="Kalkulator BEP" subtitle="BEP Unit = Fixed Cost / (Harga Jual − Variable Cost); BEP Rupiah = BEP Unit × Harga Jual" />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card-panel grid gap-4 sm:grid-cols-2">
          <Field label="Ambil dari produk (opsional)" className="sm:col-span-2"><SelectInput value={f.product_id} onChange={pick} options={(products || []).map((p) => ({ value: p.id, label: `${p.name} — jual ${formatRp(p.selling_price)}, HPP ${formatRp(p.avg_hpp, true)}` }))} data-testid="bep-product-select" /></Field>
          <Field label="Nama perhitungan" className="sm:col-span-2"><TextInput value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="bep-name-input" /></Field>
          <Field label="Fixed Cost (biaya tetap / periode)"><NumberInput value={f.fixed_cost} onChange={(v) => setF({ ...f, fixed_cost: v })} data-testid="bep-fixed-input" /></Field>
          <Field label="Harga Jual / unit"><NumberInput value={f.selling_price} onChange={(v) => setF({ ...f, selling_price: v })} data-testid="bep-price-input" /></Field>
          <Field label="Variable Cost / unit (HPP)"><NumberInput value={f.variable_cost} onChange={(v) => setF({ ...f, variable_cost: v })} data-testid="bep-variable-input" /></Field>
          <div className="flex items-end"><Button onClick={save} data-testid="bep-save-btn">Simpan Perhitungan</Button></div>
        </div>
        <div className="card-panel" data-testid="bep-result">
          <h3 className="mb-3 font-heading font-semibold">Hasil</h3>
          <SummaryRow label="Margin kontribusi / unit" value={formatRp(contrib)} tone={contrib > 0 ? "good" : "bad"} />
          <SummaryRow label="BEP Unit" value={units === null ? "—" : `${formatNum(units)} unit`} bold tone="primary" testId="bep-units" />
          <SummaryRow label="BEP Rupiah" value={units === null ? "—" : formatRp(units * price)} bold testId="bep-rupiah" />
          {contrib <= 0 && price > 0 && <p className="mt-2 rounded-md bg-red-50 p-2 text-xs text-red-700">Harga jual harus lebih besar dari biaya variabel per unit agar BEP dapat dihitung.</p>}
        </div>
      </div>
      <h3 className="mt-8 mb-3 font-heading font-semibold">Perhitungan Tersimpan</h3>
      <DataTable testId="bep-table" filename="bep" rows={saved.data || []} pageSize={5} columns={[{ key: "name", label: "Nama" }, { key: "fixed_cost", label: "Fixed Cost", align: "right", render: (r) => formatRp(r.fixed_cost) }, { key: "selling_price", label: "Harga Jual", align: "right", render: (r) => formatRp(r.selling_price) }, { key: "variable_cost", label: "Variable Cost", align: "right", render: (r) => formatRp(r.variable_cost, true) }, { label: "BEP Unit", align: "right", key: (r) => formatNum(r.result?.bep_units) }, { label: "BEP Rupiah", align: "right", key: (r) => formatRp(r.result?.bep_rupiah) }, { label: "", noExport: true, align: "right", render: (r) => <Button variant="ghost" size="sm" className="text-red-600" onClick={async () => { await api.delete(`/bep/${r.id}`); saved.reload(); }} data-testid="bep-delete-btn"><Trash2 className="h-4 w-4" /></Button> }]} />
    </div>
  );
}
