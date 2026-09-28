import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line, Legend, PieChart, Pie, Cell } from "recharts";
import { useApi, qs } from "../../lib/hooks";
import { formatRp, formatNum, formatPct, formatDate } from "../../lib/format";
import { PageHeader, StatCard, SelectInput, PeriodFilter, usePeriod, EmptyState } from "../../components/common";
import { channelOpts, statusOpts, useProducts, productOpts } from "../../lib/marketplace";

const COLORS = ["#0f766e", "#f97316", "#0ea5e9", "#a855f7", "#e11d48", "#84cc16", "#facc15"];
const short = (v) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}jt` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(0)}rb` : v);
const tip = (v, name) => [formatRp(v), name];

const Panel = ({ title, children, testId }) => <div className="card-panel" data-testid={testId}><h3 className="mb-3 font-heading text-sm font-semibold">{title}</h3><div className="h-64">{children}</div></div>;

export default function MarketplaceDashboard() {
  const period = usePeriod("month");
  const [f, setF] = useState({ channel: "", product_id: "", sku: "", status: "" });
  const { data: products } = useProducts();
  const { data } = useApi(`/marketplace/dashboard${qs({ start: period.range.start, end: period.range.end, ...f })}`);
  const s = data?.summary;
  const daily = (data?.daily || []).map((d) => ({ ...d, label: formatDate(d.key).slice(0, 6) }));
  const byCh = data?.by_channel || [];
  const byProd = (data?.by_product || []).slice(0, 8);
  const costMix = s ? [{ name: "HPP", value: s.hpp_total }, { name: "Packaging", value: s.packaging_cost }, { name: "Marketplace Fee", value: s.marketplace_fee_total }, { name: "Advertising", value: s.ad_fee }, { name: "Net Profit", value: Math.max(s.net_profit, 0) }].filter((x) => x.value > 0) : [];
  return (
    <div data-testid="marketplace-dashboard-page">
      <PageHeader title="Dashboard Marketplace" subtitle="Ringkasan penjualan Shopee, TikTok Shop, Tokopedia & Website. Order Pending/Dibatalkan tidak dihitung." />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <PeriodFilter period={period} />
        <SelectInput className="h-8 w-auto text-xs" value={f.channel} onChange={(v) => setF({ ...f, channel: v })} options={channelOpts} placeholder="Semua channel" data-testid="mp-dash-channel" />
        <SelectInput className="h-8 w-auto max-w-[220px] text-xs" value={f.product_id} onChange={(v) => setF({ ...f, product_id: v })} options={productOpts(products)} placeholder="Semua produk" data-testid="mp-dash-product" />
        <input className="field-input h-8 w-32 text-xs" placeholder="SKU" value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })} data-testid="mp-dash-sku" />
        <SelectInput className="h-8 w-auto text-xs" value={f.status} onChange={(v) => setF({ ...f, status: v })} options={statusOpts} placeholder="Semua status" data-testid="mp-dash-status" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <StatCard label="Omzet Kotor" value={formatRp(s?.gross_revenue)} testId="mp-kpi-gross" /><StatCard label="Omzet Bersih" value={formatRp(s?.net_revenue)} tone="primary" sub={s ? `Diskon ${formatRp(s.discount)} · Voucher ${formatRp(s.voucher)} · Refund ${formatRp(s.refund)}` : ""} testId="mp-kpi-net" />
        <StatCard label="HPP" value={formatRp(s?.hpp_total)} testId="mp-kpi-hpp" /><StatCard label="Biaya Packaging" value={formatRp(s?.packaging_cost)} testId="mp-kpi-packaging" />
        <StatCard label="Biaya Marketplace" value={formatRp(s?.marketplace_fee_total)} tone="accent" testId="mp-kpi-fee" /><StatCard label="Biaya Iklan" value={formatRp(s?.ad_fee)} tone="accent" testId="mp-kpi-ads" />
        <StatCard label="Gross Profit" value={formatRp(s?.gross_profit)} tone={(s?.gross_profit || 0) >= 0 ? "good" : "bad"} testId="mp-kpi-gross-profit" /><StatCard label="Net Profit" value={formatRp(s?.net_profit)} tone={(s?.net_profit || 0) >= 0 ? "good" : "bad"} testId="mp-kpi-net-profit" />
        <StatCard label="Margin" value={formatPct(s?.margin_pct)} testId="mp-kpi-margin" /><StatCard label="Jumlah Pesanan" value={formatNum(s?.order_count, 0)} sub={s ? `${s.pending_count} pending · ${s.cancelled_count} batal` : ""} testId="mp-kpi-orders" />
        <StatCard label="Qty Terjual" value={formatNum(s?.qty_sold, 0)} testId="mp-kpi-qty" /><StatCard label="AOV" value={formatRp(s?.aov)} sub="Omzet bersih / pesanan" testId="mp-kpi-aov" />
      </div>
      {!data || (data.daily.length === 0) ? <div className="mt-6 card-panel"><EmptyState text="Belum ada order pada filter ini" /></div> : (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Panel title="Omzet & Profit Harian" testId="mp-chart-daily">
            <ResponsiveContainer><LineChart data={daily}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="label" fontSize={11} /><YAxis tickFormatter={short} fontSize={11} width={48} /><Tooltip formatter={tip} /><Legend />
              <Line type="monotone" dataKey="net_revenue" name="Omzet Bersih" stroke="#0f766e" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="gross_profit" name="Gross Profit" stroke="#0ea5e9" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="net_profit" name="Net Profit" stroke="#f97316" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer>
          </Panel>
          <Panel title="Komposisi Biaya vs Net Profit" testId="mp-chart-cost-mix">
            <ResponsiveContainer><PieChart><Pie data={costMix} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>{costMix.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip formatter={tip} /><Legend /></PieChart></ResponsiveContainer>
          </Panel>
          <Panel title="Penjualan per Channel" testId="mp-chart-channel">
            <ResponsiveContainer><BarChart data={byCh}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="key" fontSize={11} /><YAxis tickFormatter={short} fontSize={11} width={48} /><Tooltip formatter={tip} /><Legend />
              <Bar dataKey="net_revenue" name="Omzet Bersih" fill="#0f766e" radius={[4, 4, 0, 0]} /><Bar dataKey="marketplace_fee_total" name="Marketplace Fee" fill="#f97316" radius={[4, 4, 0, 0]} /><Bar dataKey="net_profit" name="Net Profit" fill="#0ea5e9" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
          </Panel>
          <Panel title="Penjualan per Produk (Top 8)" testId="mp-chart-product">
            <ResponsiveContainer><BarChart data={byProd} layout="vertical" margin={{ left: 10 }}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis type="number" tickFormatter={short} fontSize={11} /><YAxis type="category" dataKey="key" width={130} fontSize={10} /><Tooltip formatter={tip} /><Legend />
              <Bar dataKey="net_revenue" name="Omzet Bersih" fill="#0f766e" radius={[0, 4, 4, 0]} /><Bar dataKey="net_profit" name="Net Profit" fill="#0ea5e9" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer>
          </Panel>
          <Panel title="HPP, Packaging, Marketplace Fee & Advertising Harian" testId="mp-chart-costs">
            <ResponsiveContainer><BarChart data={daily}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="label" fontSize={11} /><YAxis tickFormatter={short} fontSize={11} width={48} /><Tooltip formatter={tip} /><Legend />
              <Bar dataKey="hpp_total" name="HPP" stackId="c" fill="#64748b" /><Bar dataKey="packaging_cost" name="Packaging" stackId="c" fill="#a855f7" /><Bar dataKey="marketplace_fee_total" name="Marketplace Fee" stackId="c" fill="#f97316" /><Bar dataKey="ad_fee" name="Advertising" stackId="c" fill="#e11d48" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
          </Panel>
          <Panel title="Status Pesanan" testId="mp-chart-status">
            <ResponsiveContainer><BarChart data={data.by_status}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="status" fontSize={10} /><YAxis fontSize={11} width={30} allowDecimals={false} /><Tooltip /><Bar dataKey="count" name="Jumlah" fill="#0f766e" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
          </Panel>
        </div>
      )}
    </div>
  );
}
