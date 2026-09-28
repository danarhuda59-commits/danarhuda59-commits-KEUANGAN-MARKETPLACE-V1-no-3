import { useParams, Link } from "react-router-dom";
import { Printer } from "lucide-react";
import { useApi, qs } from "../lib/hooks";
import { formatRp, formatNum, formatPct, formatDate, printPage } from "../lib/format";
import { Button } from "../components/ui/button";
import { PageHeader, DataTable, PeriodFilter, usePeriod, StatCard, ReportContext } from "../components/common";
import { cn } from "../lib/utils";

const TYPES = [
  { key: "penjualan", label: "Penjualan" }, { key: "pembelian", label: "Pembelian" }, { key: "pengeluaran", label: "Pengeluaran" }, { key: "hpp", label: "HPP" }, { key: "stok", label: "Stok" },
  { key: "produksi", label: "Produksi" }, { key: "keuangan", label: "Keuangan" }, { key: "supplier", label: "Supplier" }, { key: "produk", label: "Produk" }, { key: "channel", label: "Channel" }, { key: "harga", label: "Histori Harga" },
];
const rp = (k, label) => ({ key: k, label, align: "right", render: (r) => formatRp(r[k]) });
const rpd = (k, label) => ({ key: k, label, align: "right", render: (r) => formatRp(r[k], true) });
const nm = (k, label) => ({ key: k, label, align: "right", render: (r) => formatNum(r[k]) });
const pct = (k, label) => ({ key: k, label, align: "right", render: (r) => formatPct(r[k]) });
const dt = { key: "date", label: "Tanggal", render: (r) => formatDate(r.date) };

const Section = ({ title, children }) => <div className="mb-8"><h3 className="mb-3 font-heading font-semibold">{title}</h3>{children}</div>;

function Body({ type, range, title }) {
  const url = { penjualan: "/reports/sales", pembelian: "/reports/purchases", pengeluaran: "/reports/expenses", hpp: "/reports/hpp", stok: "/inventory/summary", produksi: "/reports/production", keuangan: "/reports/profit-loss", supplier: "/reports/suppliers", produk: "/reports/products", channel: "/reports/channels", harga: "/reports/price-history" }[type];
  const { data: d, loading } = useApi(`${url}${qs(range)}`, [range.start, range.end, type]);
  if (!d || loading) return <p className="text-sm text-muted-foreground">Memuat...</p>;
  const expectArray = ["stok", "supplier", "produk", "channel", "harga"].includes(type);
  if (expectArray !== Array.isArray(d)) return <p className="text-sm text-muted-foreground">Memuat...</p>;
  switch (type) {
    case "penjualan": return (<>
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"><StatCard label="Omzet bersih" value={formatRp(d.summary.net_sales)} tone="primary" /><StatCard label="HPP" value={formatRp(d.summary.hpp)} /><StatCard label="Laba kotor" value={formatRp(d.summary.gross_profit)} tone="good" /><StatCard label="Transaksi" value={d.summary.transactions} /></div>
      <Section title="Per Produk"><DataTable testId="rpt-sales-products" filename="laporan-penjualan-produk" rows={d.by_product} columns={[{ key: "product_name", label: "Produk" }, { key: "sku", label: "SKU" }, nm("qty", "Qty"), rp("avg_price", "Harga Jual"), rpd("hpp_per_unit", "HPP/Unit"), rp("omzet", "Omzet"), rp("hpp", "HPP"), rp("profit", "Laba"), pct("margin_pct", "Margin")]} /></Section>
      <Section title="Per Channel"><DataTable testId="rpt-sales-channels" filename="laporan-penjualan-channel" rows={d.by_channel} columns={[{ key: "channel", label: "Channel" }, { key: "count", label: "Transaksi", align: "right" }, rp("omzet", "Omzet"), rp("fees", "Biaya"), rp("net", "Bersih"), rp("hpp", "HPP"), rp("profit", "Laba"), pct("margin_pct", "Margin")]} /></Section>
      <Section title="Detail Transaksi"><DataTable testId="rpt-sales-detail" filename="laporan-penjualan" rows={d.sales} loading={loading} searchKeys={["number", "channel"]} columns={[{ key: "number", label: "Nomor" }, dt, { key: "channel", label: "Channel" }, { label: "Produk", key: (r) => r.items.map((i) => `${i.product_name} ×${formatNum(i.qty)}`).join(", ") }, nm("qty_total", "Qty"), rp("total", "Total"), rp("net_total", "Bersih"), rp("total_hpp", "HPP"), rp("profit", "Laba")]} /></Section>
    </>);
    case "pembelian": return (<>
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3"><StatCard label="Total pembelian" value={formatRp(d.total)} /><StatCard label="Transaksi" value={d.count} /><StatCard label="Belum dibayar" value={formatRp(d.unpaid)} tone="accent" /></div>
      <Section title="Per Supplier"><DataTable testId="rpt-purchase-suppliers" filename="pembelian-supplier" rows={d.by_supplier} columns={[{ key: "supplier", label: "Supplier" }, { key: "count", label: "Transaksi", align: "right" }, rp("total", "Total"), rp("paid", "Dibayar"), rp("unpaid", "Hutang")]} /></Section>
      <Section title="Per Bahan"><DataTable testId="rpt-purchase-materials" filename="pembelian-bahan" rows={d.by_material} columns={[{ key: "material", label: "Bahan" }, nm("qty", "Qty"), { key: "unit", label: "Satuan" }, rp("avg_price", "Harga Rata2"), rp("total", "Total")]} /></Section>
      <Section title="Detail"><DataTable testId="rpt-purchase-detail" filename="laporan-pembelian" rows={d.purchases} columns={[{ key: "number", label: "Nomor" }, dt, { key: "supplier_name", label: "Supplier" }, { label: "Item", key: (r) => r.items.map((i) => `${i.material_name} ${formatNum(i.qty)} ${i.unit}`).join(", ") }, rp("total", "Total"), rp("paid_amount", "Dibayar"), { key: "payment_status", label: "Status" }]} /></Section>
    </>);
    case "pengeluaran": return (<>
      <div className="mb-6 grid grid-cols-2 gap-3"><StatCard label="Total pengeluaran" value={formatRp(d.total)} tone="accent" /><StatCard label="Jumlah" value={d.count} /></div>
      <Section title="Per Kategori"><DataTable testId="rpt-expense-cat" filename="pengeluaran-kategori" rows={d.by_category} columns={[{ key: "category", label: "Kategori" }, rp("amount", "Total")]} /></Section>
      <Section title="Detail"><DataTable testId="rpt-expense-detail" filename="laporan-pengeluaran" rows={d.expenses} columns={[dt, { key: "number", label: "Nomor" }, { key: "category", label: "Kategori" }, { key: "description", label: "Deskripsi" }, rp("amount", "Nominal"), { key: "payment_method", label: "Metode" }]} /></Section>
    </>);
    case "hpp": return (<>
      <Section title="HPP Resep Saat Ini (harga bahan terkini)"><DataTable testId="rpt-hpp-current" filename="hpp-resep" rows={d.current} columns={[{ key: "recipe_name", label: "Resep" }, { key: "product_name", label: "Produk" }, { key: "item_count", label: "Bahan", align: "right" }, rpd("material_total", "Total Bahan"), rpd("total_batch", "HPP Batch"), nm("yield_qty", "Yield"), rpd("hpp_per_unit", "HPP/Unit"), rp("selling_price", "Harga Jual"), pct("margin_pct", "Margin"), pct("markup_pct", "Markup")]} /></Section>
      <Section title="Histori HPP Produksi (snapshot, tidak berubah)"><DataTable testId="rpt-hpp-history" filename="hpp-produksi" rows={d.history} columns={[{ key: "number", label: "Nomor" }, dt, { key: "product_name", label: "Produk" }, { key: "recipe_name", label: "Resep" }, nm("qty_produced", "Qty"), rpd("material_total", "Bahan"), rpd("packaging_total", "Kemasan"), rpd("labor_total", "Tenaga Kerja"), rpd("overhead_total", "Overhead"), rpd("other_total", "Lainnya"), rpd("total_cost", "Total"), rpd("hpp_per_unit", "HPP/Unit")]} /></Section>
    </>);
    case "stok": return (<>
      <Section title="Bahan Baku"><DataTable testId="rpt-stock-materials" filename="laporan-stok-bahan" rows={d.filter((r) => r.item_type === "material")} columns={[{ key: "code", label: "Kode" }, { key: "name", label: "Nama" }, { key: "unit", label: "Satuan" }, nm("opening", "Stok Awal"), nm("in_qty", "Masuk"), nm("out_qty", "Keluar"), nm("adjustment", "Adj"), nm("closing", "Stok Akhir"), nm("min_stock", "Min"), rpd("unit_cost", "Harga/Satuan"), rp("stock_value", "Nilai Stok"), { key: "is_low_stock", label: "Status", render: (r) => (r.is_low_stock ? <span className="badge-low">Rendah</span> : <span className="badge-ok">Aman</span>) }]} /></Section>
      <Section title="Produk Jadi"><DataTable testId="rpt-stock-products" filename="laporan-stok-produk" rows={d.filter((r) => r.item_type === "product")} columns={[{ key: "code", label: "SKU" }, { key: "name", label: "Nama" }, { key: "unit", label: "Satuan" }, nm("opening", "Stok Awal"), nm("in_qty", "Masuk"), nm("out_qty", "Keluar"), nm("adjustment", "Adj"), nm("closing", "Stok Akhir"), nm("min_stock", "Min"), rpd("unit_cost", "HPP/Unit"), rp("stock_value", "Nilai Stok")]} /></Section>
    </>);
    case "produksi": return (<>
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3"><StatCard label="Produksi" value={d.count} /><StatCard label="Total unit" value={formatNum(d.total_qty)} /><StatCard label="Total biaya produksi" value={formatRp(d.total_cost)} /></div>
      <Section title="Per Produk"><DataTable testId="rpt-prod-products" filename="produksi-produk" rows={d.by_product} columns={[{ key: "product", label: "Produk" }, { key: "count", label: "Batch produksi", align: "right" }, nm("qty", "Total Unit"), rp("cost", "Total Biaya"), rpd("avg_hpp", "HPP Rata2/Unit")]} /></Section>
      <Section title="Detail"><DataTable testId="rpt-prod-detail" filename="laporan-produksi" rows={d.production} columns={[{ key: "number", label: "Nomor" }, dt, { key: "product_name", label: "Produk" }, { key: "recipe_name", label: "Resep" }, nm("batch_count", "Batch"), nm("qty_produced", "Qty"), rpd("total_cost", "Total Biaya"), rpd("hpp_per_unit", "HPP/Unit"), { key: "operator", label: "Operator" }]} /></Section>
    </>);
    case "keuangan": { const s = d.summary; const rows = [["Omzet (bruto)", s.omzet], ["Biaya platform/layanan", -s.sales_fees], ["Penjualan bersih", s.net_sales], ["HPP penjualan", -s.hpp], ["LABA KOTOR", s.gross_profit], ["Beban operasional", -s.opex], ["LABA BERSIH", s.net_profit]].map(([label, value]) => ({ label, value }));
      return (<>
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"><StatCard label="Penjualan bersih" value={formatRp(s.net_sales)} tone="primary" /><StatCard label="Laba kotor" value={formatRp(s.gross_profit)} sub={formatPct(s.gross_margin_pct)} tone="good" /><StatCard label="Beban operasional" value={formatRp(s.opex)} tone="accent" /><StatCard label="Laba bersih" value={formatRp(s.net_profit)} sub={formatPct(s.net_margin_pct)} tone={s.net_profit >= 0 ? "good" : "bad"} /></div>
        <Section title="Laba Rugi"><DataTable testId="rpt-finance-pl" filename="laporan-keuangan" rows={rows} pageSize={20} columns={[{ key: "label", label: "Pos" }, rp("value", "Nilai")]} /></Section>
        <Section title="Beban per Kategori"><DataTable testId="rpt-finance-exp" filename="beban-kategori" rows={d.expenses_by_category} columns={[{ key: "category", label: "Kategori" }, rp("amount", "Nominal")]} /></Section>
        <p className="text-sm text-muted-foreground">Lihat juga <Link className="text-primary underline" to="/cash-flow">Laporan Cash Flow</Link> dan <Link className="text-primary underline" to="/laba-rugi">Laba Rugi detail</Link>.</p>
      </>); }
    case "supplier": return <DataTable testId="rpt-suppliers" filename="laporan-supplier" rows={d} columns={[{ key: "code", label: "Kode" }, { key: "name", label: "Supplier" }, { key: "contact_name", label: "Kontak" }, { key: "phone", label: "Telepon" }, { key: "purchase_count", label: "Transaksi", align: "right" }, rp("total", "Total Pembelian"), rp("unpaid", "Hutang"), { key: "last_date", label: "Terakhir", render: (r) => (r.last_date === "-" ? "-" : formatDate(r.last_date)) }]} />;
    case "produk": return <DataTable testId="rpt-products" filename="laporan-produk" rows={d} columns={[{ key: "sku", label: "SKU" }, { key: "name", label: "Produk" }, nm("stock", "Stok"), rpd("avg_hpp", "HPP/Unit"), rp("selling_price", "Harga Jual"), pct("current_margin_pct", "Margin saat ini"), rp("stock_value", "Nilai Stok"), nm("sold_qty", "Terjual"), rp("omzet", "Omzet"), rp("hpp_sold", "HPP Terjual"), rp("profit", "Laba"), pct("margin_pct", "Margin Realisasi")]} />;
    case "channel": return <DataTable testId="rpt-channels" filename="laporan-channel" rows={d} columns={[{ key: "channel", label: "Channel" }, { key: "count", label: "Transaksi", align: "right" }, nm("qty", "Qty"), rp("omzet", "Omzet"), rp("fees", "Biaya Platform"), rp("net", "Bersih"), rp("hpp", "HPP"), rp("profit", "Laba"), pct("margin_pct", "Margin")]} />;
    case "harga": return <DataTable testId="rpt-prices" filename="histori-harga" rows={d} searchKeys={["material_name", "supplier_name"]} columns={[dt, { key: "material_name", label: "Bahan" }, rp("price", "Harga"), { key: "unit", label: "Satuan" }, { key: "supplier_name", label: "Supplier" }, { key: "source", label: "Sumber" }]} />;
    default: return null;
  }
}

export default function Reports() {
  const { type = "penjualan" } = useParams();
  const period = usePeriod("month");
  const cur = TYPES.find((t) => t.key === type) || TYPES[0];
  return (
    <div data-testid="reports-page">
      <PageHeader title={`Laporan ${cur.label}`} subtitle="Filter tanggal, cari, export CSV/Excel, dan print" actions={<><Button variant="outline" size="sm" onClick={printPage} data-testid="export-csv-btn"><Printer className="mr-1 h-4 w-4" />Print / PDF</Button><PeriodFilter period={period} /></>} />
      <div className="mb-6 flex flex-wrap gap-1 no-print" data-testid="report-tabs">
        {TYPES.map((t) => <Link key={t.key} to={`/laporan/${t.key}`} data-testid={`report-tab-${t.key}`} className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", t.key === cur.key ? "bg-slate-900 text-white border-slate-900" : "hover:bg-muted")}>{t.label}</Link>)}
      </div>
      <ReportContext.Provider value={{ title: `Laporan ${cur.label}`, period: period.range }}><Body type={cur.key} range={period.range} /></ReportContext.Provider>
    </div>
  );
}
