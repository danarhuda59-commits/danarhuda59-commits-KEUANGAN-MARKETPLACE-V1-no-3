import { useState } from "react";
import { toast } from "sonner";
import { SlidersHorizontal } from "lucide-react";
import { api, errMsg } from "../lib/api";
import { useApi, qs } from "../lib/hooks";
import { formatRp, formatNum, formatDate, todayISO } from "../lib/format";
import { PageHeader, DataTable, Modal, Field, TextInput, NumberInput, SelectInput, PeriodFilter, usePeriod, StatCard } from "../components/common";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Button } from "../components/ui/button";

const REASONS = { purchase: "Pembelian", production: "Produksi", sale: "Penjualan", adjustment: "Adjustment", waste: "Waste/Rusak", return: "Retur", reversal: "Pembatalan", initial: "Stok awal" };

export default function Stock() {
  const period = usePeriod("month");
  const [tab, setTab] = useState("material");
  const { data: summary, loading, reload } = useApi(`/inventory/summary${qs(period.range)}`, [period.range.start, period.range.end]);
  const { data: ledger, reload: reloadLedger } = useApi(`/inventory/transactions${qs(period.range)}`, [period.range.start, period.range.end]);
  const [adj, setAdj] = useState(null);
  const rows = (summary || []).filter((r) => r.item_type === tab);
  const totalValue = rows.reduce((a, r) => a + r.stock_value, 0);
  const lowCount = rows.filter((r) => r.is_low_stock).length;
  const saveAdj = async () => {
    if (!(parseFloat(adj.qty) > 0)) return toast.error("Qty harus lebih dari 0");
    try { await api.post("/inventory/adjust", { ...adj, qty: parseFloat(adj.qty) }); toast.success("Penyesuaian stok tercatat"); setAdj(null); reload(); reloadLedger(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="stock-page">
      <PageHeader title="Stok & Inventory" subtitle="Ledger transaksi stok — bukan hanya angka akhir" actions={<PeriodFilter period={period} />} />
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label={`Nilai stok ${tab === "material" ? "bahan" : "produk"}`} value={formatRp(totalValue)} testId="stock-total-value" />
        <StatCard label="Item" value={rows.length} testId="stock-item-count" />
        <StatCard label="Stok rendah" value={lowCount} tone={lowCount ? "accent" : "good"} testId="stock-low-count" />
      </div>
      <Tabs value={tab} onValueChange={setTab} className="mb-4"><TabsList><TabsTrigger value="material" data-testid="stock-tab-material">Bahan Baku</TabsTrigger><TabsTrigger value="product" data-testid="stock-tab-product">Produk Jadi</TabsTrigger></TabsList></Tabs>
      <DataTable testId="stock-table" filename={`stok-${tab}`} rows={rows} loading={loading} searchKeys={["name", "code"]} columns={[
        { key: "code", label: "Kode" }, { key: "name", label: "Nama" }, { key: "unit", label: "Satuan" },
        { key: "opening", label: "Stok Awal", align: "right", render: (r) => formatNum(r.opening) }, { key: "in_qty", label: "Masuk", align: "right", render: (r) => <span className="text-emerald-700">{formatNum(r.in_qty)}</span> },
        { key: "out_qty", label: "Keluar", align: "right", render: (r) => <span className="text-red-600">{formatNum(r.out_qty)}</span> }, { key: "adjustment", label: "Adjustment", align: "right", render: (r) => formatNum(r.adjustment) },
        { key: "closing", label: "Stok Akhir", align: "right", render: (r) => <b>{formatNum(r.closing)}</b> }, { key: "current_stock", label: "Stok Saat Ini", align: "right", render: (r) => <span className={r.is_low_stock ? "text-orange-600 font-semibold" : ""}>{formatNum(r.current_stock)}{r.is_low_stock && <span className="ml-1 badge-low">Rendah</span>}</span> },
        { key: "min_stock", label: "Min", align: "right", render: (r) => formatNum(r.min_stock) }, { key: "unit_cost", label: "Harga/Satuan", align: "right", render: (r) => formatRp(r.unit_cost, true) }, { key: "stock_value", label: "Nilai Stok", align: "right", render: (r) => formatRp(r.stock_value) },
        { label: "", noExport: true, align: "right", render: (r) => <Button variant="outline" size="sm" onClick={() => setAdj({ item_type: r.item_type, item_id: r.item_id, name: r.name, qty: "", direction: "in", reason: "adjustment", date: todayISO(), note: "" })} data-testid="stock-adjust-btn"><SlidersHorizontal className="mr-1 h-3.5 w-3.5" />Sesuaikan</Button> },
      ]} />
      <h3 className="mt-8 mb-3 font-heading font-semibold">Riwayat Pergerakan Stok</h3>
      <DataTable testId="ledger-table" filename="ledger-stok" rows={(ledger || []).filter((t) => t.item_type === tab)} searchKeys={["item_name", "reason", "note"]} columns={[
        { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "item_name", label: "Item" }, { key: "reason", label: "Jenis", render: (r) => REASONS[r.reason] || r.reason },
        { key: "direction", label: "Arah", render: (r) => (r.direction === "in" ? <span className="badge-ok">Masuk</span> : <span className="badge-low">Keluar</span>) }, { key: "qty", label: "Qty", align: "right", render: (r) => `${formatNum(r.qty)} ${r.unit || ""}` },
        { key: "unit_cost", label: "Harga/Satuan", align: "right", render: (r) => formatRp(r.unit_cost, true) }, { key: "total_cost", label: "Nilai", align: "right", render: (r) => formatRp(r.total_cost) }, { key: "balance_after", label: "Saldo Setelah", align: "right", render: (r) => formatNum(r.balance_after) }, { key: "note", label: "Catatan" },
      ]} />
      <Modal open={!!adj} onClose={() => setAdj(null)} title={`Penyesuaian Stok — ${adj?.name}`} footer={<><Button variant="outline" onClick={() => setAdj(null)}>Batal</Button><Button onClick={saveAdj} data-testid="adjust-save-btn">Simpan</Button></>}>
        {adj && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Arah"><SelectInput value={adj.direction} onChange={(v) => setAdj({ ...adj, direction: v })} allowEmpty={false} options={[{ value: "in", label: "Stok Masuk (+)" }, { value: "out", label: "Stok Keluar (−)" }]} data-testid="adjust-direction-select" /></Field>
          <Field label="Alasan"><SelectInput value={adj.reason} onChange={(v) => setAdj({ ...adj, reason: v })} allowEmpty={false} options={[{ value: "adjustment", label: "Adjustment / Opname" }, { value: "waste", label: "Waste / Rusak" }, { value: "return", label: "Retur" }]} data-testid="adjust-reason-select" /></Field>
          <Field label="Qty" required><NumberInput value={adj.qty} onChange={(v) => setAdj({ ...adj, qty: v })} data-testid="adjust-qty-input" /></Field>
          <Field label="Tanggal"><TextInput type="date" value={adj.date} onChange={(e) => setAdj({ ...adj, date: e.target.value })} data-testid="adjust-date-input" /></Field>
          <Field label="Catatan" className="sm:col-span-2"><TextInput value={adj.note} onChange={(e) => setAdj({ ...adj, note: e.target.value })} data-testid="adjust-note-input" /></Field>
        </div>}
      </Modal>
    </div>
  );
}
