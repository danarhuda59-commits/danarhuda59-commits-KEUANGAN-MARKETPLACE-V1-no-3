import { useState } from "react";
import { toast } from "sonner";
import { Download, Upload, Database, Trash2, Sparkles, Users, Building2, FileUp } from "lucide-react";
import { api, errMsg, API } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useAuth } from "../lib/auth";
import { formatDateTime } from "../lib/format";
import { PageHeader, Field, TextInput, NumberInput, SelectInput, TextArea, ConfirmDialog, DataTable, Modal } from "../components/common";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Button } from "../components/ui/button";

const IMPORT_TYPES = [{ value: "materials", label: "Bahan Baku" }, { value: "products", label: "Produk" }, { value: "suppliers", label: "Supplier" }, { value: "recipes", label: "Resep" }, { value: "purchases", label: "Pembelian" }, { value: "sales", label: "Penjualan" }];

function Profile() {
  const { business, refresh } = useAuth();
  const [f, setF] = useState({ name: business?.name || "", address: business?.address || "", phone: business?.phone || "", email: business?.email || "", target_margin: business?.target_margin ?? 30, notes: business?.notes || "" });
  const [pw, setPw] = useState({ old_password: "", new_password: "" });
  const save = async () => { try { await api.put("/business", { ...f, target_margin: parseFloat(f.target_margin || 0) }); toast.success("Profil usaha tersimpan"); refresh(); } catch (e) { toast.error(errMsg(e)); } };
  const changePw = async () => { try { await api.post("/auth/change-password", pw); toast.success("Password diubah"); setPw({ old_password: "", new_password: "" }); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card-panel grid gap-4 sm:grid-cols-2" data-testid="business-profile-form">
        <h3 className="font-heading font-semibold sm:col-span-2 flex items-center gap-2"><Building2 className="h-4 w-4" />Profil Usaha</h3>
        <Field label="Nama Usaha" required className="sm:col-span-2"><TextInput value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="business-name-input" /></Field>
        <Field label="Telepon"><TextInput value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} data-testid="business-phone-input" /></Field>
        <Field label="Email"><TextInput value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Target margin default (%)"><NumberInput value={f.target_margin} onChange={(v) => setF({ ...f, target_margin: v })} /></Field>
        <Field label="Alamat" className="sm:col-span-2"><TextArea value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Button onClick={save} data-testid="business-save-btn">Simpan Profil</Button></div>
      </div>
      <div className="card-panel space-y-4">
        <h3 className="font-heading font-semibold">Ganti Password</h3>
        <Field label="Password lama"><TextInput type="password" value={pw.old_password} onChange={(e) => setPw({ ...pw, old_password: e.target.value })} data-testid="old-password-input" /></Field>
        <Field label="Password baru (min 6)"><TextInput type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} data-testid="new-password-input" /></Field>
        <Button variant="outline" onClick={changePw} data-testid="change-password-btn">Ubah Password</Button>
      </div>
    </div>
  );
}

function UsersTab() {
  const { user } = useAuth();
  const { data, reload } = useApi("/users");
  const [f, setF] = useState(null);
  const save = async () => { try { await api.post("/users", f); toast.success("User ditambahkan"); setF(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center"><p className="text-sm text-muted-foreground">Semua user di bawah ini hanya dapat mengakses data usaha Anda.</p>{user?.role === "owner" && <Button onClick={() => setF({ name: "", email: "", password: "", role: "staff" })} data-testid="user-add-btn"><Users className="mr-1 h-4 w-4" />Tambah User</Button>}</div>
      <DataTable testId="users-table" filename="users" rows={data || []} columns={[{ key: "name", label: "Nama" }, { key: "email", label: "Email" }, { key: "role", label: "Role" }, { label: "Dibuat", key: (r) => formatDateTime(r.created_at) }, { label: "", noExport: true, align: "right", render: (r) => (user?.role === "owner" && r.id !== user.id ? <Button variant="ghost" size="sm" className="text-red-600" onClick={async () => { try { await api.delete(`/users/${r.id}`); reload(); } catch (e) { toast.error(errMsg(e)); } }} data-testid="user-delete-btn"><Trash2 className="h-4 w-4" /></Button> : null) }]} />
      <Modal open={!!f} onClose={() => setF(null)} title="Tambah User" footer={<><Button variant="outline" onClick={() => setF(null)}>Batal</Button><Button onClick={save} data-testid="user-save-btn">Simpan</Button></>}>
        {f && <div className="grid gap-4 sm:grid-cols-2"><Field label="Nama" required><TextInput value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="user-name-input" /></Field><Field label="Email" required><TextInput type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} data-testid="user-email-input" /></Field><Field label="Password" required><TextInput type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} data-testid="user-password-input" /></Field><Field label="Role"><SelectInput value={f.role} onChange={(v) => setF({ ...f, role: v })} allowEmpty={false} options={[{ value: "staff", label: "Staff" }, { value: "admin", label: "Admin" }, { value: "owner", label: "Owner" }]} /></Field></div>}
      </Modal>
    </div>
  );
}

function BackupTab() {
  const [busy, setBusy] = useState(false);
  const [restoreFile, setRestoreFile] = useState(null);
  const download = async () => {
    setBusy(true);
    try { const { data } = await api.get("/backup"); const blob = new Blob([JSON.stringify(data)], { type: "application/json" }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `backup-${new Date().toISOString().slice(0, 10)}.json`; a.click(); toast.success("Backup diunduh"); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const restore = async () => {
    setBusy(true);
    try { const fd = new FormData(); fd.append("file", restoreFile); const { data } = await api.post("/restore", fd); toast.success(`Restore selesai: ${Object.values(data.restored).reduce((a, b) => a + b, 0)} record`); setRestoreFile(null); setTimeout(() => window.location.reload(), 800); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card-panel space-y-3"><h3 className="font-heading font-semibold flex items-center gap-2"><Database className="h-4 w-4" />Backup Data</h3><p className="text-sm text-muted-foreground">Unduh seluruh data usaha (master, transaksi, ledger, kas) dalam satu file JSON.</p><Button onClick={download} disabled={busy} data-testid="backup-download-btn"><Download className="mr-1 h-4 w-4" />Download Backup</Button></div>
      <div className="card-panel space-y-3"><h3 className="font-heading font-semibold flex items-center gap-2"><Upload className="h-4 w-4" />Restore Data</h3><p className="text-sm text-red-600">Perhatian: restore akan mengganti seluruh data usaha saat ini dengan isi file backup.</p><input type="file" accept="application/json" onChange={(e) => setRestoreFile(e.target.files?.[0] || null)} className="text-sm" data-testid="restore-file-input" />{restoreFile && <ConfirmRestore onConfirm={restore} busy={busy} />}</div>
    </div>
  );
}
function ConfirmRestore({ onConfirm, busy }) { const [open, setOpen] = useState(false); return <><Button variant="destructive" onClick={() => setOpen(true)} disabled={busy} data-testid="restore-btn">Restore Sekarang</Button><ConfirmDialog open={open} onClose={() => setOpen(false)} onConfirm={() => { setOpen(false); onConfirm(); }} title="Restore data?" description="Seluruh data saat ini akan diganti dengan isi backup." confirmText="Ya, Restore" /></>; }

function ImportTab() {
  const [type, setType] = useState("materials");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const doPreview = async () => {
    if (!file) return toast.error("Pilih file CSV/Excel terlebih dahulu");
    setBusy(true);
    try { const fd = new FormData(); fd.append("itype", type); fd.append("file", file); const { data } = await api.post("/import/preview", fd); setPreview(data); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const commit = async () => {
    setBusy(true);
    try { const rows = preview.rows.filter((r) => !r.errors.length).map((r) => ({ ...r.data, _row: r.row })); const { data } = await api.post("/import/commit", { type, rows }); toast.success(`${data.imported} data berhasil diimport${data.errors.length ? `, ${data.errors.length} gagal` : ""}`); if (data.errors.length) toast.error(data.errors.slice(0, 3).join(" | ")); setPreview(null); setFile(null); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const tplUrl = `${API}/import/template/${type}?auth=${localStorage.getItem("token")}`;
  return (
    <div className="space-y-6">
      <div className="card-panel grid gap-4 sm:grid-cols-[200px_1fr_auto_auto] items-end">
        <Field label="Jenis data"><SelectInput value={type} onChange={(v) => { setType(v); setPreview(null); }} allowEmpty={false} options={IMPORT_TYPES} data-testid="import-type-select" /></Field>
        <Field label="File CSV / Excel"><input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); }} className="text-sm" data-testid="import-file-input" /></Field>
        <a href={tplUrl} className="inline-flex h-10 items-center rounded-md border px-3 text-sm hover:bg-muted" data-testid="import-template-link"><Download className="mr-1 h-4 w-4" />Template</a>
        <Button onClick={doPreview} disabled={busy} data-testid="import-preview-btn"><FileUp className="mr-1 h-4 w-4" />Preview</Button>
      </div>
      {preview && (
        <div className="card-panel space-y-3" data-testid="import-preview">
          <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm"><b>{preview.valid_count}</b> baris valid, <b className="text-red-600">{preview.error_count}</b> baris error. Hanya baris valid yang akan diimport.</p><Button onClick={commit} disabled={busy || preview.valid_count === 0} data-testid="import-commit-btn">Konfirmasi Import ({preview.valid_count})</Button></div>
          <div className="table-wrap max-h-96 overflow-auto"><table><thead><tr><th>Baris</th>{preview.columns.map((c) => <th key={c}>{c}</th>)}<th>Status</th></tr></thead>
            <tbody>{preview.rows.map((r) => <tr key={r.row} className={r.errors.length ? "bg-red-50 dark:bg-red-900/20" : ""}><td>{r.row}</td>{preview.columns.map((c) => <td key={c} className="max-w-[160px] truncate">{String(r.data[c] ?? "")}</td>)}<td className="text-xs">{r.errors.length ? <span className="text-red-600">{r.errors.join("; ")}</span> : <span className="badge-ok">OK</span>}</td></tr>)}</tbody></table></div>
        </div>
      )}
      <p className="text-xs text-muted-foreground">Export CSV/Excel tersedia di setiap tabel & laporan melalui tombol CSV / Excel / Print.</p>
    </div>
  );
}

function DemoTab() {
  const { data, reload } = useApi("/demo/status");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const seed = async () => { setBusy(true); try { await api.post("/demo/seed"); toast.success("Demo data dibuat: bahan, supplier, produk, resep, pembelian, produksi, penjualan, pengeluaran"); reload(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); } };
  const remove = async () => { setBusy(true); try { const { data } = await api.delete("/demo"); toast.success(`Demo data dihapus (${Object.values(data.removed).reduce((a, b) => a + b, 0)} record)`); setConfirm(false); reload(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); } };
  const logs = useApi("/audit-logs?limit=100");
  return (
    <div className="space-y-6">
      <div className="card-panel flex flex-wrap items-center justify-between gap-4">
        <div><h3 className="font-heading font-semibold flex items-center gap-2"><Sparkles className="h-4 w-4" />Demo Data</h3><p className="text-sm text-muted-foreground">Data contoh generik (bukan merek tertentu) untuk mencoba seluruh alur aplikasi. Status: <b data-testid="demo-status">{data?.has_demo ? "Demo data aktif" : "Tidak ada demo data"}</b></p></div>
        <div className="flex gap-2">{!data?.has_demo && <Button onClick={seed} disabled={busy} data-testid="demo-seed-btn">Muat Demo Data</Button>}{data?.has_demo && <Button variant="destructive" onClick={() => setConfirm(true)} disabled={busy} data-testid="demo-delete-btn"><Trash2 className="mr-1 h-4 w-4" />Hapus Semua Demo Data</Button>}</div>
      </div>
      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} onConfirm={remove} loading={busy} title="Hapus semua demo data?" description="Semua data yang ditandai demo (bahan, produk, resep, transaksi, ledger, kas) akan dihapus permanen. Data non-demo tetap aman." confirmText="Hapus Demo Data" />
      <div><h3 className="mb-3 font-heading font-semibold">Audit Log</h3><DataTable testId="audit-table" filename="audit-log" rows={logs.data || []} columns={[{ label: "Waktu", key: (r) => formatDateTime(r.created_at) }, { key: "user_name", label: "User" }, { key: "action", label: "Aksi" }, { key: "entity", label: "Entitas" }, { label: "Detail", key: (r) => JSON.stringify(r.detail || {}) }]} /></div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div data-testid="settings-page">
      <PageHeader title="Pengaturan" subtitle="Profil usaha, user, backup/restore, import/export, demo data" />
      <Tabs defaultValue="profil">
        <TabsList className="mb-6 flex-wrap h-auto"><TabsTrigger value="profil" data-testid="settings-tab-profil">Profil Usaha</TabsTrigger><TabsTrigger value="user" data-testid="settings-tab-user">User</TabsTrigger><TabsTrigger value="backup" data-testid="settings-tab-backup">Backup</TabsTrigger><TabsTrigger value="import" data-testid="settings-tab-import">Import/Export</TabsTrigger><TabsTrigger value="demo" data-testid="settings-tab-demo">Demo Data & Audit</TabsTrigger></TabsList>
        <TabsContent value="profil"><Profile /></TabsContent><TabsContent value="user"><UsersTab /></TabsContent><TabsContent value="backup"><BackupTab /></TabsContent><TabsContent value="import"><ImportTab /></TabsContent><TabsContent value="demo"><DemoTab /></TabsContent>
      </Tabs>
    </div>
  );
}
