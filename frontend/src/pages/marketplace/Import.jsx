import { useState } from "react";
import { toast } from "sonner";
import { Upload, ArrowRight, CheckCircle2, AlertTriangle, Copy } from "lucide-react";
import { api, errMsg } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { formatRp, formatNum, formatDate, formatDateTime } from "../../lib/format";
import { PageHeader, Field, SelectInput, StatCard, EmptyState, DataTable } from "../../components/common";
import { Button } from "../../components/ui/button";
import { channelOpts, statusOpts, StatusBadge, ChannelBadge } from "../../lib/marketplace";
import { cn } from "../../lib/utils";

const STEPS = ["Upload", "Preview", "Mapping Kolom", "Validasi & Duplikasi", "Konfirmasi"];

function Stepper({ step }) {
  return (
    <ol className="mb-6 flex flex-wrap gap-2 text-xs" data-testid="import-stepper">
      {STEPS.map((s, i) => <li key={s} className={cn("flex items-center gap-1 rounded-full border px-3 py-1", i === step ? "border-primary bg-primary text-primary-foreground" : i < step ? "border-emerald-300 text-emerald-700" : "text-muted-foreground")}>{i < step && <CheckCircle2 className="h-3 w-3" />}{i + 1}. {s}</li>)}
    </ol>
  );
}

export default function MarketplaceImport() {
  const [step, setStep] = useState(0);
  const [channel, setChannel] = useState("Shopee");
  const [file, setFile] = useState(null);
  const [prev, setPrev] = useState(null);
  const [mapping, setMapping] = useState({});
  const [defaultStatus, setDefaultStatus] = useState("Selesai");
  const [val, setVal] = useState(null);
  const [includeDup, setIncludeDup] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const { data: history, reload: reloadHistory } = useApi("/marketplace/import/history");

  const upload = async () => {
    if (!file) return toast.error("Pilih file CSV/Excel");
    const fd = new FormData(); fd.append("channel", channel); fd.append("file", file);
    try { setBusy(true); const { data } = await api.post("/marketplace/import/preview", fd); setPrev(data); setMapping(data.suggested_mapping); setStep(1); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const validate = async () => {
    try { setBusy(true); const { data } = await api.post("/marketplace/import/validate", { channel, mapping, rows: prev.rows, default_status: defaultStatus }); setVal(data); setStep(3); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const selected = (val?.rows || []).filter((r) => r.errors.length === 0 && (includeDup || !r.duplicate));
  const commit = async () => {
    try { setBusy(true); const { data } = await api.post("/marketplace/import/commit", { channel, filename: prev.filename, rows: selected }); setResult(data); toast.success(`${data.imported} order diimpor`); reloadHistory(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const reset = () => { setStep(0); setFile(null); setPrev(null); setMapping({}); setVal(null); setResult(null); setIncludeDup(false); };
  const colOpts = (prev?.columns || []).map((c) => ({ value: c, label: c }));

  return (
    <div data-testid="marketplace-import-page">
      <PageHeader title="Import Marketplace" subtitle="Upload → Preview → Mapping Kolom → Validasi & Deteksi Duplikasi → Konfirmasi. Data tidak disimpan sebelum Anda menekan Konfirmasi Import." />
      <Stepper step={result ? 4 : step} />
      {step === 0 && (
        <div className="card-panel max-w-xl space-y-4" data-testid="import-step-upload">
          <Field label="Channel" required><SelectInput value={channel} onChange={setChannel} options={channelOpts} allowEmpty={false} data-testid="import-channel" /></Field>
          <Field label="File CSV / Excel" required hint="Export pesanan dari Seller Center Shopee / TikTok Shop / Tokopedia atau data website. Produk dikenali via SKU atau Nama Produk yang sama dengan master Produk.">
            <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] || null)} className="field-input h-auto py-1.5" data-testid="import-file" />
          </Field>
          <Button onClick={upload} disabled={busy || !file} data-testid="import-upload-btn"><Upload className="mr-1 h-4 w-4" />Upload & Preview</Button>
        </div>
      )}
      {step === 1 && prev && (
        <div className="space-y-4" data-testid="import-step-preview">
          <div className="flex flex-wrap items-center gap-3 text-sm"><ChannelBadge channel={channel} /><span><b>{prev.filename}</b> · {prev.row_count} baris · {prev.columns.length} kolom</span></div>
          <div className="table-wrap max-h-[420px]"><table><thead><tr>{prev.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{prev.rows.slice(0, 20).map((r, i) => <tr key={i}>{prev.columns.map((c) => <td key={c} className="max-w-[200px] truncate">{r[c]}</td>)}</tr>)}</tbody></table></div>
          {prev.row_count > 20 && <p className="text-xs text-muted-foreground">Menampilkan 20 dari {prev.row_count} baris.</p>}
          <div className="flex gap-2"><Button variant="outline" onClick={reset}>Ulang</Button><Button onClick={() => setStep(2)} data-testid="import-to-mapping-btn">Lanjut ke Mapping<ArrowRight className="ml-1 h-4 w-4" /></Button></div>
        </div>
      )}
      {step === 2 && prev && (
        <div className="space-y-4" data-testid="import-step-mapping">
          <p className="text-sm text-muted-foreground">Petakan kolom file ke field sistem. Kolom yang terdeteksi otomatis sudah terisi; periksa kembali. Field bertanda * wajib.</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {prev.fields.map((f) => (
              <Field key={f.key} label={f.label} required={f.required}><SelectInput value={mapping[f.key] || ""} onChange={(v) => setMapping({ ...mapping, [f.key]: v })} options={colOpts} placeholder="— tidak dipetakan —" data-testid={`import-map-${f.key}`} /></Field>
            ))}
            <Field label="Status default (bila kolom status kosong/tidak dipetakan)"><SelectInput value={defaultStatus} onChange={setDefaultStatus} options={statusOpts} allowEmpty={false} data-testid="import-default-status" /></Field>
          </div>
          <div className="flex gap-2"><Button variant="outline" onClick={() => setStep(1)}>Kembali</Button><Button onClick={validate} disabled={busy} data-testid="import-validate-btn">Validasi<ArrowRight className="ml-1 h-4 w-4" /></Button></div>
        </div>
      )}
      {step === 3 && val && !result && (
        <div className="space-y-4" data-testid="import-step-validate">
          <div className="grid gap-3 sm:grid-cols-4">
            <StatCard label="Total Baris" value={val.rows.length} testId="import-kpi-total" /><StatCard label="Valid & Baru" value={val.valid_count} tone="good" testId="import-kpi-valid" /><StatCard label="Error" value={val.error_count} tone="bad" testId="import-kpi-error" /><StatCard label="Duplikat (Order ID + SKU)" value={val.duplicate_count} tone="accent" testId="import-kpi-dup" />
          </div>
          {val.duplicate_count > 0 && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeDup} onChange={(e) => setIncludeDup(e.target.checked)} className="h-4 w-4 accent-teal-700" data-testid="import-include-dup" />Tetap impor baris duplikat dari <b>file</b> (duplikat yang sudah ada di database akan selalu dilewati)</label>}
          <div className="table-wrap max-h-[460px]">
            <table><thead><tr><th>Baris</th><th>Order ID</th><th>Tanggal</th><th>Produk / SKU</th><th className="text-right">Qty</th><th className="text-right">Harga</th><th className="text-right">Diskon+Voucher</th><th>Status</th><th>Hasil</th></tr></thead>
              <tbody>{val.rows.map((r) => (
                <tr key={r.row} className={r.errors.length ? "bg-red-50/60 dark:bg-red-950/20" : r.duplicate ? "bg-orange-50/60 dark:bg-orange-950/20" : ""} data-testid="import-validate-row">
                  <td>{r.row}</td><td className="font-medium">{r.data.order_id || <i className="text-muted-foreground">kosong</i>}</td><td>{formatDate(r.data.date)}</td><td>{r.data.product_name}{r.data.sku && <span className="text-muted-foreground"> ({r.data.sku})</span>}</td>
                  <td className="text-right num">{formatNum(r.data.qty)}</td><td className="text-right num">{formatRp(r.data.selling_price)}</td><td className="text-right num">{formatRp((r.data.discount || 0) + (r.data.voucher || 0))}</td><td><StatusBadge status={r.data.status} /></td>
                  <td className="text-xs">
                    {r.errors.map((e, i) => <p key={i} className="flex items-start gap-1 text-red-600"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /><span><b>{e.field}</b> = "{e.value}": {e.reason}</span></p>)}
                    {r.duplicate && <p className="flex items-center gap-1 text-orange-600"><Copy className="h-3 w-3" />Duplikat ({r.duplicate_source === "database" ? "sudah ada di database" : "ganda di file"})</p>}
                    {!r.errors.length && !r.duplicate && <span className="text-emerald-700">OK</span>}
                  </td>
                </tr>))}</tbody></table>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => setStep(2)}>Kembali ke Mapping</Button>
            <Button onClick={commit} disabled={busy || selected.length === 0} data-testid="import-commit-btn"><CheckCircle2 className="mr-1 h-4 w-4" />Konfirmasi Import ({selected.length} baris)</Button>
          </div>
        </div>
      )}
      {result && (
        <div className="card-panel space-y-3" data-testid="import-result">
          <h3 className="font-heading font-semibold">Import selesai</h3>
          <div className="grid gap-3 sm:grid-cols-4"><StatCard label="Diimpor" value={result.imported} tone="good" testId="import-result-imported" /><StatCard label="Dilewati (duplikat DB)" value={result.skipped_duplicates} testId="import-result-skipped" /><StatCard label="Gagal" value={result.errors.length} tone="bad" /><StatCard label="Peringatan stok" value={result.warnings.length} tone="accent" /></div>
          {result.errors.map((e, i) => <p key={i} className="text-sm text-red-600">Baris {e.row} ({e.order_id}): {e.reason}</p>)}
          {result.warnings.map((w, i) => <p key={i} className="text-sm text-orange-600">Baris {w.row} ({w.order_id}): {w.reason} — order tersimpan, stok belum dikurangi</p>)}
          <Button onClick={reset} data-testid="import-again-btn">Import lagi</Button>
        </div>
      )}
      <div className="mt-10">
        <h3 className="mb-3 font-heading font-semibold">Riwayat Import</h3>
        {(history || []).length === 0 ? <EmptyState text="Belum ada import" /> : <DataTable rows={history} filename="Riwayat Import" testId="import-history-table" pageSize={5} columns={[
          { key: "created_at", label: "Waktu", render: (r) => formatDateTime(r.created_at) }, { key: "channel", label: "Channel", render: (r) => <ChannelBadge channel={r.channel} /> }, { key: "filename", label: "File" },
          { key: "rows_total", label: "Baris", align: "right" }, { key: "imported", label: "Diimpor", align: "right" }, { key: "skipped_duplicates", label: "Duplikat", align: "right" }, { label: "Gagal", align: "right", key: (r) => r.errors.length },
        ]} />}
      </div>
    </div>
  );
}
