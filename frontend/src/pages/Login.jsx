import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useAuth } from "../lib/auth";
import { errMsg } from "../lib/api";
import { Field, TextInput } from "../components/common";
import { Button } from "../components/ui/button";

export default function Login() {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "", business_name: "" });
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const nav = useNavigate();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(mode === "login" ? { email: form.email, password: form.password } : form, mode);
      toast.success(mode === "login" ? "Selamat datang kembali" : "Akun berhasil dibuat");
      nav("/");
    } catch (err) { toast.error(errMsg(err)); } finally { setLoading(false); }
  };
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between bg-slate-900 p-12 text-slate-200">
        <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-600 font-heading text-xl font-bold text-white">H</div><span className="font-heading text-lg font-semibold text-white">Business Finance & HPP</span></div>
        <div className="max-w-md space-y-6">
          <h1 className="font-heading text-4xl font-bold leading-tight text-white">Hitung HPP akurat, kelola stok & keuangan UMKM dalam satu sistem.</h1>
          <ul className="space-y-2 text-sm text-slate-400">
            <li>• Resep/BOM multi-bahan dinamis dengan konversi satuan & waste</li>
            <li>• Snapshot HPP historis — harga lama tidak berubah</li>
            <li>• Stock ledger terintegrasi: pembelian → produksi → penjualan</li>
            <li>• Laba rugi, cash flow, BEP, dan laporan lengkap</li>
          </ul>
        </div>
        <p className="text-xs text-slate-500">Dirancang untuk UMKM produksi makanan & minuman</p>
      </div>
      <div className="flex items-center justify-center p-6 sm:p-12">
        <form onSubmit={submit} className="w-full max-w-md space-y-5 fade-up" data-testid="auth-form">
          <div>
            <h2 className="font-heading text-2xl font-bold">{mode === "login" ? "Masuk" : "Daftar Akun Baru"}</h2>
            <p className="text-sm text-muted-foreground">{mode === "login" ? "Masuk untuk mengelola usaha Anda" : "Buat akun dan profil usaha Anda"}</p>
          </div>
          {mode === "register" && (<>
            <Field label="Nama Lengkap" required><TextInput required value={form.name} onChange={set("name")} data-testid="register-name-input" /></Field>
            <Field label="Nama Usaha" required><TextInput required value={form.business_name} onChange={set("business_name")} data-testid="register-business-input" /></Field>
          </>)}
          <Field label="Email" required><TextInput type="email" required value={form.email} onChange={set("email")} data-testid="login-email-input" /></Field>
          <Field label="Password" required><TextInput type="password" required minLength={6} value={form.password} onChange={set("password")} data-testid="login-password-input" /></Field>
          <Button type="submit" className="w-full" disabled={loading} data-testid="login-submit-btn">{loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}{mode === "login" ? "Masuk" : "Daftar"}</Button>
          <p className="text-center text-sm text-muted-foreground">
            {mode === "login" ? "Belum punya akun? " : "Sudah punya akun? "}
            <button type="button" className="font-medium text-primary hover:underline" onClick={() => setMode(mode === "login" ? "register" : "login")} data-testid="auth-toggle-mode-btn">{mode === "login" ? "Daftar" : "Masuk"}</button>
          </p>
        </form>
      </div>
    </div>
  );
}
