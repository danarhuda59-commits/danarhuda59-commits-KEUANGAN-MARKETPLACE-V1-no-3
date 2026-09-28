import { useState } from "react";
import { toast } from "sonner";
import { Calculator } from "lucide-react";
import { api, errMsg } from "../../lib/api";
import { formatRp, formatNum, formatDate, todayISO } from "../../lib/format";
import { CrudPage } from "../MasterData";
import { Field, NumberInput, SelectInput, TextInput, SummaryRow } from "../../components/common";
import { Button } from "../../components/ui/button";
import { channelOpts, ChannelBadge } from "../../lib/marketplace";

const CATS = [{ value: "admin", label: "Biaya Admin" }, { value: "service", label: "Biaya Layanan" }, { value: "transaction", label: "Biaya Transaksi" }, { value: "other", label: "Biaya Marketplace Lainnya" }];
const catLabel = (v) => CATS.find((c) => c.value === v)?.label || v;

function FeeSimulator() {
  const [f, setF] = useState({ channel: "Shopee", date: todayISO(), base: "100000" });
  const [res, setRes] = useState(null);
  const run = async () => {
    try { const { data } = await api.get(`/marketplace/fees/preview?channel=${encodeURIComponent(f.channel)}&date=${f.date}&base=${f.base || 0}`); setRes(data); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="card-panel" data-testid="fee-simulator">
      <h3 className="mb-1 font-heading font-semibold">Simulasi Biaya Channel</h3>
      <p className="mb-4 text-sm text-muted-foreground">Cek total potongan yang akan dihitung otomatis untuk sebuah nilai penjualan pada tanggal tertentu.</p>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Channel"><SelectInput value={f.channel} onChange={(v) => setF({ ...f, channel: v })} options={channelOpts} allowEmpty={false} data-testid="fee-sim-channel" /></Field>
        <Field label="Tanggal"><TextInput type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} data-testid="fee-sim-date" /></Field>
        <Field label="Nilai Penjualan (Rp)"><NumberInput value={f.base} onChange={(v) => setF({ ...f, base: v })} data-testid="fee-sim-base" /></Field>
        <div className="flex items-end"><Button onClick={run} data-testid="fee-sim-run"><Calculator className="mr-1 h-4 w-4" />Hitung</Button></div>
      </div>
      {res && (
        <div className="mt-4 max-w-md" data-testid="fee-sim-result">
          {res.detail.length === 0 && <p className="text-sm text-muted-foreground">Tidak ada biaya aktif untuk channel/tanggal ini.</p>}
          {res.detail.map((d) => <SummaryRow key={d.fee_id} label={`${d.name} (${d.fee_type === "percent" ? `${formatNum(d.value)}%` : "nominal"})`} value={formatRp(d.amount)} />)}
          <SummaryRow label="Total potongan" value={formatRp(res.total)} bold tone="bad" testId="fee-sim-total" />
        </div>
      )}
    </div>
  );
}

export default function ChannelFees() {
  return (
    <div className="space-y-8">
      <CrudPage title="Pengaturan Biaya Channel" subtitle="Biaya admin, layanan, transaksi per marketplace — persentase atau nominal, dengan periode berlaku. Tidak ada persentase yang di-hardcode." endpoint="/marketplace/fees" testId="fees"
        emptyForm={{ name: "", channel: "Shopee", category: "admin", fee_type: "percent", value: "", valid_from: "", valid_to: "", is_active: true, notes: "" }}
        columns={[
          { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> }, { key: "name", label: "Nama Biaya" }, { key: "category", label: "Kategori", render: (r) => catLabel(r.category) },
          { key: "value", label: "Nilai", align: "right", render: (r) => (r.fee_type === "percent" ? `${formatNum(r.value)}%` : formatRp(r.value)) },
          { key: "valid_from", label: "Berlaku Mulai", render: (r) => (r.valid_from ? formatDate(r.valid_from) : "-") }, { key: "valid_to", label: "Berlaku Sampai", render: (r) => (r.valid_to ? formatDate(r.valid_to) : "-") },
          { key: "is_active", label: "Status", render: (r) => <span className={r.is_active ? "badge-ok" : "badge-muted"}>{r.is_active ? "Aktif" : "Nonaktif"}</span>, export: (r) => (r.is_active ? "Aktif" : "Nonaktif") },
        ]}
        fields={[
          { name: "name", label: "Nama Biaya", required: true, hint: "contoh: Admin Fee, Service Fee, Transaction Fee" }, { name: "channel", label: "Channel", type: "select", options: channelOpts, required: true },
          { name: "category", label: "Kategori", type: "select", options: CATS, hint: "Menentukan kolom biaya pada transaksi" }, { name: "fee_type", label: "Tipe", type: "select", options: [{ value: "percent", label: "Persentase (%)" }, { value: "nominal", label: "Nominal (Rp)" }] },
          { name: "value", label: "Nilai", type: "number", required: true, hint: (f) => (f.fee_type === "percent" ? "% dari harga jual × qty − diskon − voucher" : "Rp per pesanan") }, { name: "valid_from", label: "Berlaku Mulai", type: "date" },
          { name: "valid_to", label: "Berlaku Sampai", type: "date", hint: "Kosongkan bila tidak ada batas" }, { name: "notes", label: "Catatan" }, { name: "is_active", label: "Aktif", type: "checkbox" },
        ]}
        validate={(f) => (!f.name?.trim() ? "Nama biaya wajib diisi" : f.value === "" ? "Nilai wajib diisi" : null)}
        transformOut={(f) => ({ ...f, value: parseFloat(f.value) || 0 })} />
      <FeeSimulator />
    </div>
  );
}
