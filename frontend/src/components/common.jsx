import { createContext, useContext, useMemo, useState } from "react";
import { toast } from "sonner";
import { Search, Download, FileSpreadsheet, FileText, Printer, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import { exportCSV, exportExcel, exportPDF, printPage, PERIODS, periodRange } from "../lib/format";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";

export const PageHeader = ({ title, subtitle, actions, testId }) => (
  <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between fade-up" data-testid={testId || "page-header"}>
    <div>
      <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
    </div>
    {actions && <div className="flex flex-wrap gap-2 no-print">{actions}</div>}
  </div>
);

const tones = {
  default: "text-slate-900 dark:text-slate-100", good: "text-emerald-700 dark:text-emerald-400", bad: "text-red-600 dark:text-red-400", accent: "text-orange-600 dark:text-orange-400", primary: "text-teal-700 dark:text-teal-300",
};
export const StatCard = ({ label, value, sub, icon: Icon, tone = "default", testId }) => (
  <div className="stat-card fade-up" data-testid={testId}>
    <div className="flex items-start justify-between gap-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
    </div>
    <p className={cn("mt-2 text-xl sm:text-2xl font-bold num truncate", tones[tone])}>{value}</p>
    {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
  </div>
);

export const Field = ({ label, children, hint, required, className }) => (
  <label className={cn("flex flex-col gap-1.5 text-sm", className)}>
    {label && <span className="font-medium text-slate-700 dark:text-slate-300">{label}{required && <span className="text-red-500"> *</span>}</span>}
    {children}
    {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
  </label>
);

export const TextInput = (props) => <input {...props} className={cn("field-input", props.className)} />;
export const NumberInput = ({ value, onChange, min = 0, step = "any", ...rest }) => (
  <input type="number" inputMode="decimal" min={min} step={step} value={value ?? ""} onChange={(e) => onChange(e.target.value)} {...rest} className={cn("field-input num", rest.className)} />
);
export const TextArea = (props) => <textarea {...props} className={cn("field-input min-h-[80px]", props.className)} />;
export const SelectInput = ({ options = [], placeholder = "Pilih...", value, onChange, allowEmpty = true, ...rest }) => (
  <select value={value ?? ""} onChange={(e) => onChange(e.target.value)} {...rest} className={cn("field-input", rest.className)}>
    {allowEmpty && <option value="">{placeholder}</option>}
    {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>
);

export const Modal = ({ open, onClose, title, description, children, footer, wide }) => (
  <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
    <DialogContent className={cn("max-h-[92vh] overflow-y-auto", wide ? "max-w-5xl" : "max-w-2xl")} data-testid="modal">
      <DialogHeader>
        <DialogTitle className="font-heading">{title}</DialogTitle>
        {description ? <DialogDescription>{description}</DialogDescription> : <DialogDescription className="sr-only">Form</DialogDescription>}
      </DialogHeader>
      <div className="space-y-4">{children}</div>
      {footer && <DialogFooter className="gap-2">{footer}</DialogFooter>}
    </DialogContent>
  </Dialog>
);

export const ConfirmDialog = ({ open, onClose, onConfirm, title = "Konfirmasi", description = "Tindakan ini tidak dapat dibatalkan.", confirmText = "Hapus", loading }) => (
  <AlertDialog open={open} onOpenChange={(v) => !v && onClose()}>
    <AlertDialogContent data-testid="confirm-dialog">
      <AlertDialogHeader>
        <AlertDialogTitle>{title}</AlertDialogTitle>
        <AlertDialogDescription>{description}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel data-testid="confirm-cancel-btn">Batal</AlertDialogCancel>
        <AlertDialogAction data-testid="confirm-ok-btn" onClick={onConfirm} disabled={loading} className="bg-red-600 hover:bg-red-700">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : confirmText}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
);

export const EmptyState = ({ text = "Belum ada data" }) => <div className="py-10 text-center text-sm text-muted-foreground" data-testid="empty-state">{text}</div>;

export const ReportContext = createContext({ title: "", period: null });

export const ExportButtons = ({ rows, columns, filename, title }) => {
  const ctx = useContext(ReportContext);
  const { business } = useAuth();
  const pdf = () => exportPDF(rows, columns, filename, { business: business?.name, title: title || ctx.title || filename, period: ctx.period }).catch((e) => toast.error(`PDF gagal: ${e.message}`));
  return (
    <div className="flex gap-1 no-print">
      <Button variant="outline" size="sm" data-testid="export-csv-btn" onClick={() => exportCSV(rows, columns, filename)}><Download className="h-4 w-4 sm:mr-1" /><span className="hidden sm:inline">CSV</span></Button>
      <Button variant="outline" size="sm" data-testid="export-excel-btn" onClick={() => exportExcel(rows, columns, filename)}><FileSpreadsheet className="h-4 w-4 sm:mr-1" /><span className="hidden sm:inline">Excel</span></Button>
      <Button variant="outline" size="sm" data-testid="export-pdf-btn" onClick={pdf}><FileText className="h-4 w-4 sm:mr-1" /><span className="hidden sm:inline">PDF</span></Button>
      <Button variant="outline" size="sm" data-testid="print-btn" onClick={printPage}><Printer className="h-4 w-4 sm:mr-1" /><span className="hidden sm:inline">Print</span></Button>
    </div>
  );
};

export function DataTable({ columns, rows = [], searchKeys, pageSize = 10, filename = "data", testId = "data-table", toolbar, emptyText, loading, onRowClick, footer, title }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const filtered = useMemo(() => {
    if (!q) return rows;
    const s = q.toLowerCase();
    return rows.filter((r) => (searchKeys || columns.map((c) => c.key).filter((k) => typeof k === "string")).some((k) => String(r[k] ?? "").toLowerCase().includes(s)));
  }, [rows, q, searchKeys, columns]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const cur = Math.min(page, pages);
  const slice = filtered.slice((cur - 1) * pageSize, cur * pageSize);
  return (
    <div className="space-y-3" data-testid={testId}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between no-print">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Cari..." className="field-input pl-9" data-testid={`${testId}-search`} />
        </div>
        <div className="flex flex-wrap items-center gap-2">{toolbar}<ExportButtons rows={filtered} columns={columns} filename={filename} title={title} /></div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{columns.map((c, i) => <th key={i} className={c.align === "right" ? "text-right" : ""}>{c.label}</th>)}</tr></thead>
          <tbody>
            {loading ? <tr><td colSpan={columns.length}><div className="py-8 text-center"><Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" /></div></td></tr>
              : slice.length === 0 ? <tr><td colSpan={columns.length}><EmptyState text={emptyText} /></td></tr>
              : slice.map((r, ri) => (
                <tr key={r.id || ri} onClick={onRowClick ? () => onRowClick(r) : undefined} className={onRowClick ? "cursor-pointer" : ""} data-testid={`${testId}-row`}>
                  {columns.map((c, ci) => <td key={ci} className={cn(c.align === "right" && "text-right num", c.className)}>{c.render ? c.render(r) : typeof c.key === "function" ? c.key(r) : r[c.key]}</td>)}
                </tr>
              ))}
          </tbody>
          {footer && <tfoot>{footer(filtered)}</tfoot>}
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground no-print">
        <span data-testid={`${testId}-count`}>{filtered.length} data</span>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" disabled={cur <= 1} onClick={() => setPage(cur - 1)} data-testid="page-prev"><ChevronLeft className="h-4 w-4" /></Button>
          <span>Hal {cur} / {pages}</span>
          <Button variant="ghost" size="sm" disabled={cur >= pages} onClick={() => setPage(cur + 1)} data-testid="page-next"><ChevronRight className="h-4 w-4" /></Button>
        </div>
      </div>
    </div>
  );
}

export function usePeriod(initial = "month") {
  const [key, setKey] = useState(initial);
  const [range, setRange] = useState(periodRange(initial));
  const change = (k) => { setKey(k); if (k !== "custom") setRange(periodRange(k)); };
  return { key, range, change, setRange };
}

export const PeriodFilter = ({ period, className }) => (
  <div className={cn("flex flex-wrap items-center gap-2 no-print", className)} data-testid="period-filter">
    <div className="flex flex-wrap gap-1 rounded-lg border bg-card p-1">
      {PERIODS.map((p) => (
        <button key={p.key} onClick={() => period.change(p.key)} data-testid={`period-${p.key}`}
          className={cn("rounded-md px-2.5 py-1 text-xs font-medium transition-colors", period.key === p.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>{p.label}</button>
      ))}
    </div>
    {period.key === "custom" && (
      <div className="flex items-center gap-1">
        <input type="date" className="field-input h-8 w-auto text-xs" value={period.range.start} onChange={(e) => period.setRange({ ...period.range, start: e.target.value })} data-testid="period-start" />
        <span className="text-xs">s/d</span>
        <input type="date" className="field-input h-8 w-auto text-xs" value={period.range.end} onChange={(e) => period.setRange({ ...period.range, end: e.target.value })} data-testid="period-end" />
      </div>
    )}
  </div>
);

export const SummaryRow = ({ label, value, bold, tone, testId }) => (
  <div className={cn("flex items-center justify-between gap-4 py-1.5 text-sm", bold && "border-t pt-2 font-semibold")} data-testid={testId}>
    <span className="text-muted-foreground">{label}</span>
    <span className={cn("num font-medium", tones[tone] || "")}>{value}</span>
  </div>
);
