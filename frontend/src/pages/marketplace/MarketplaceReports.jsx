import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useApi, qs } from "../../lib/hooks";
import { formatRp, formatNum, formatPct, formatDate } from "../../lib/format";
import { PageHeader, DataTable, StatCard, SelectInput, PeriodFilter, usePeriod, ReportContext } from "../../components/common";
import { channelOpts, StatusBadge, ChannelBadge, useProducts, productOpts } from "../../lib/marketplace";
import { cn } from "../../lib/utils";

const rp = (k, label) => ({ key: k, label, align: "right", render: (r) => formatRp(r[k]) });
const base = [{ key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "order_id", label: "Order ID" }, { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> }, { key: "product_name", label: "Produk" }, { key: "sku", label: "SKU" }, { key: "qty", label: "Qty", align: "right", render: (r) => formatNum(r.qty) }];
const status = { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> };
const grp = (label) => [{ key: "key", label, render: (r) => (label === "Tanggal" ? formatDate(r.key) : r.key.replace("|", " · ")) }, { key: "order_count", label: "Pesanan", align: "right" }, { key: "qty_sold", label: "Qty", align: "right", render: (r) => formatNum(r.qty_sold) }, rp("gross_revenue", "Omzet Kotor"), rp("net_revenue", "Omzet Bersih"), rp("hpp_total", "HPP"), rp("packaging_cost", "Packaging"), rp("marketplace_fee_total", "Marketplace Fee"), rp("ad_fee", "Advertising"), rp("gross_profit", "Gross Profit"), rp("net_profit", "Net Profit"), { key: "margin_pct", label: "Margin %", align: "right", render: (r) => formatPct(r.margin_pct) }];

export const MP_REPORTS = {
  sales: { title: "Laporan Penjualan Marketplace", cols: [...base, { key: "customer", label: "Customer" }, rp("selling_price", "Harga Jual"), rp("discount", "Diskon"), rp("voucher", "Voucher"), rp("refund", "Refund"), rp("gross_revenue", "Omzet Kotor"), rp("net_revenue", "Omzet Bersih"), rp("customer_paid", "Dibayar Customer"), rp("seller_received", "Diterima Seller"), status] },
  hpp: { title: "Laporan HPP Marketplace", cols: [...base, rp("hpp_unit", "HPP / Unit"), rp("hpp_total", "HPP Total"), rp("net_revenue", "Omzet Bersih"), rp("gross_profit", "Gross Profit"), status] },
  packaging: { title: "Laporan Biaya Packaging", cols: [...base, { key: "packaging_name", label: "Packaging", render: (r) => r.packaging_name || "-" }, rp("packaging_cost_per_unit", "Biaya / Unit"), rp("packaging_cost", "Total Packaging"), rp("hpp_total", "HPP (terpisah)"), status] },
  "marketplace-fee": { title: "Laporan Marketplace Fee", cols: [...base, rp("admin_fee", "Biaya Admin"), rp("service_fee", "Biaya Layanan"), rp("transaction_fee", "Biaya Transaksi"), rp("other_marketplace_fee", "Biaya MP Lain"), rp("marketplace_fee_total", "Total Fee"), { key: "fee_source", label: "Sumber" }, status] },
  advertising: { title: "Laporan Advertising", cols: [...base, rp("ad_fee", "Biaya Iklan"), rp("net_revenue", "Omzet Bersih"), { label: "Iklan / Omzet %", align: "right", key: (r) => (r.net_revenue > 0 ? (r.ad_fee / r.net_revenue) * 100 : 0), render: (r) => formatPct(r.net_revenue > 0 ? (r.ad_fee / r.net_revenue) * 100 : 0) }, rp("net_profit", "Net Profit"), status] },
  settlement: { title: "Laporan Settlement", cols: [{ key: "settlement_date", label: "Tanggal", render: (r) => formatDate(r.settlement_date) }, { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> }, { key: "settlement_id", label: "Settlement ID" }, { key: "order_id", label: "Order ID" }, rp("gross_sales", "Gross Sales"), rp("marketplace_fee", "Marketplace Fee"), rp("advertising_fee", "Advertising"), rp("refund", "Refund"), rp("expected_payout", "Expected Payout"), rp("actual_payout", "Actual Payout"), rp("difference", "Selisih"), status, { key: "payment_account_name", label: "Akun" }] },
  reconciliation: { title: "Laporan Rekonsiliasi", cols: [{ key: "date", label: "Tanggal", render: (r) => formatDate(r.date) }, { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> }, { key: "order_id", label: "Order ID" }, { key: "products", label: "Produk" }, rp("total_sales", "Total Penjualan"), rp("total_deductions", "Total Potongan"), rp("expected_payout", "Expected Payout"), rp("actual_payout", "Actual Payout"), rp("difference", "Selisih"), status] },
  profit: { title: "Laporan Profit Harian", cols: grp("Tanggal") },
  products: { title: "Laporan per Produk", cols: grp("Produk · SKU") },
  channels: { title: "Laporan per Channel", cols: grp("Channel") },
};

export default function MarketplaceReports() {
  const { type } = useParams();
  const cfg = MP_REPORTS[type] || MP_REPORTS.sales;
  const period = usePeriod("month");
  const [f, setF] = useState({ channel: "", product_id: "", sku: "" });
  const { data: products } = useProducts();
  const { data, loading } = useApi(`/marketplace/reports/${type in MP_REPORTS ? type : "sales"}${qs({ start: period.range.start, end: period.range.end, ...f })}`);
  const s = data?.summary;
  return (
    <ReportContext.Provider value={{ title: cfg.title, period: period.range }}>
      <div data-testid={`mp-report-${type}`}>
        <PageHeader title={cfg.title} subtitle="Filter periode, channel, produk, SKU. Export Excel / CSV / PDF dari toolbar tabel." />
        <div className="mb-4 flex flex-wrap gap-1 no-print" data-testid="mp-report-tabs">
          {Object.entries(MP_REPORTS).map(([k, v]) => <Link key={k} to={`/marketplace/laporan/${k}`} className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", k === type ? "bg-primary text-primary-foreground border-primary" : "hover:bg-muted")} data-testid={`mp-report-tab-${k}`}>{v.title.replace("Laporan ", "")}</Link>)}
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <PeriodFilter period={period} />
          <SelectInput className="h-8 w-auto text-xs" value={f.channel} onChange={(v) => setF({ ...f, channel: v })} options={channelOpts} placeholder="Semua channel" data-testid="mp-report-channel" />
          {!["settlement", "reconciliation"].includes(type) && <><SelectInput className="h-8 w-auto max-w-[220px] text-xs" value={f.product_id} onChange={(v) => setF({ ...f, product_id: v })} options={productOpts(products)} placeholder="Semua produk" data-testid="mp-report-product" /><input className="field-input h-8 w-32 text-xs" placeholder="SKU" value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })} data-testid="mp-report-sku" /></>}
        </div>
        {s && (type === "settlement" ? (
          <div className="mb-4 grid gap-3 sm:grid-cols-4"><StatCard label="Gross Sales" value={formatRp(s.gross_sales)} /><StatCard label="Expected Payout" value={formatRp(s.expected_payout)} tone="primary" /><StatCard label="Actual Payout" value={formatRp(s.actual_payout)} tone="good" /><StatCard label="Selisih" value={formatRp(s.difference)} tone={Math.abs(s.difference) >= 1 ? "bad" : "good"} /></div>
        ) : type === "reconciliation" ? (
          <div className="mb-4 grid gap-3 sm:grid-cols-4"><StatCard label="Total Penjualan" value={formatRp(s.total_sales)} /><StatCard label="Expected Payout" value={formatRp(s.expected_payout)} tone="primary" /><StatCard label="Actual Payout" value={formatRp(s.actual_payout)} tone="good" /><StatCard label="Selisih" value={formatRp(s.difference)} tone={Math.abs(s.difference) >= 1 ? "bad" : "good"} /></div>
        ) : (
          <div className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6"><StatCard label="Omzet Bersih" value={formatRp(s.net_revenue)} tone="primary" testId="mp-report-kpi-net" /><StatCard label="HPP" value={formatRp(s.hpp_total)} /><StatCard label="Packaging" value={formatRp(s.packaging_cost)} /><StatCard label="Marketplace Fee" value={formatRp(s.marketplace_fee_total)} tone="accent" /><StatCard label="Advertising" value={formatRp(s.ad_fee)} tone="accent" /><StatCard label="Net Profit" value={formatRp(s.net_profit)} sub={`Margin ${formatPct(s.margin_pct)}`} tone={s.net_profit >= 0 ? "good" : "bad"} testId="mp-report-kpi-profit" /></div>
        ))}
        <DataTable loading={loading} rows={data?.rows || []} columns={cfg.cols} filename={cfg.title} title={cfg.title} testId="mp-report-table" pageSize={20} />
      </div>
    </ReportContext.Provider>
  );
}
