import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, Link } from "react-router-dom";
import { LayoutDashboard, Package, Boxes, Truck, Tags, Ruler, BookOpen, Factory, Warehouse, ShoppingCart, Receipt, Wallet, Landmark, TrendingUp, ArrowLeftRight, Target, FileBarChart, Settings, LogOut, Menu, X, Calculator, Sun, Moon, Bell, Store, PackageOpen, Percent, Upload, Banknote, ClipboardList } from "lucide-react";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";
import { cn } from "../lib/utils";

const NAV = [
  { items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard }] },
  { group: "Master Data", items: [{ to: "/bahan", label: "Bahan Baku", icon: Package }, { to: "/produk", label: "Produk", icon: Boxes }, { to: "/supplier", label: "Supplier", icon: Truck }, { to: "/kategori", label: "Kategori", icon: Tags }, { to: "/satuan", label: "Satuan", icon: Ruler }] },
  { group: "Produksi", items: [{ to: "/resep", label: "Resep / BOM", icon: BookOpen }, { to: "/hpp", label: "Perhitungan HPP", icon: Calculator }, { to: "/produksi", label: "Produksi", icon: Factory }, { to: "/stok", label: "Stok", icon: Warehouse }] },
  { group: "Transaksi", items: [{ to: "/pembelian", label: "Pembelian", icon: ShoppingCart }, { to: "/penjualan", label: "Penjualan", icon: Receipt }, { to: "/pengeluaran", label: "Pengeluaran", icon: Wallet }] },
  { group: "Marketplace", items: [{ to: "/marketplace", label: "Dashboard Marketplace", icon: Store }, { to: "/marketplace/order", label: "Order Marketplace", icon: ClipboardList }, { to: "/marketplace/import", label: "Import Marketplace", icon: Upload }, { to: "/marketplace/packaging", label: "Biaya Beban Packaging", icon: PackageOpen }, { to: "/marketplace/biaya", label: "Pengaturan Biaya Channel", icon: Percent }, { to: "/marketplace/settlement", label: "Settlement & Rekonsiliasi", icon: Banknote }, { to: "/marketplace/laporan/sales", label: "Laporan Marketplace", icon: FileBarChart }] },
  { group: "Keuangan", items: [{ to: "/kas", label: "Kas", icon: Landmark }, { to: "/laba-rugi", label: "Laba Rugi", icon: TrendingUp }, { to: "/cash-flow", label: "Cash Flow", icon: ArrowLeftRight }, { to: "/bep", label: "BEP", icon: Target }] },
  { group: "Laporan", items: [{ to: "/laporan/penjualan", label: "Penjualan", icon: FileBarChart }, { to: "/laporan/pembelian", label: "Pembelian", icon: FileBarChart }, { to: "/laporan/hpp", label: "HPP", icon: FileBarChart }, { to: "/laporan/stok", label: "Stok", icon: FileBarChart }, { to: "/laporan/produksi", label: "Produksi", icon: FileBarChart }, { to: "/laporan/keuangan", label: "Keuangan", icon: FileBarChart }] },
  { group: "Pengaturan", items: [{ to: "/pengaturan", label: "Pengaturan", icon: Settings }] },
];

function Sidebar({ onNavigate }) {
  const { business } = useAuth();
  return (
    <div className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="flex h-16 items-center gap-3 border-b border-slate-800 px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-teal-600 font-heading text-lg font-bold text-white">H</div>
        <div className="min-w-0">
          <p className="truncate font-heading text-sm font-semibold text-white" data-testid="sidebar-business-name">{business?.name || "HPP System"}</p>
          <p className="text-[11px] text-slate-400">Finance & HPP</p>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-3">
        {NAV.map((g, i) => (
          <div key={i}>
            {g.group && <p className="mt-4 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{g.group}</p>}
            {g.items.map((it) => (
              <NavLink key={it.to} to={it.to} end={it.to === "/" || it.to === "/marketplace"} onClick={onNavigate} data-testid={`nav-${it.to.replace(/\//g, "-").replace(/^-/, "") || "dashboard"}`}
                className={({ isActive }) => cn("mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors", isActive ? "bg-teal-600/20 text-teal-300 font-medium" : "hover:bg-slate-800 hover:text-white")}>
                <it.icon className="h-4 w-4 shrink-0" />{it.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const [desktop, setDesktop] = useState(() => window.matchMedia("(min-width: 1024px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const h = (e) => { setDesktop(e.matches); if (e.matches) setOpen(false); };
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, []);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const { user, logout } = useAuth();
  const { data: alerts } = useApi("/alerts/stock");
  const nav = useNavigate();
  const toggleDark = () => {
    const d = !dark;
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
    localStorage.setItem("theme", d ? "dark" : "light");
  };
  return (
    <div className="min-h-screen bg-background">
      {desktop && <aside className="fixed inset-y-0 left-0 z-40 w-64 no-print"><Sidebar /></aside>}
      {open && !desktop && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 shadow-xl"><Sidebar onNavigate={() => setOpen(false)} /></aside>
          <button className="absolute left-72 top-3 ml-2 rounded-full bg-white p-2 shadow" onClick={() => setOpen(false)} data-testid="sidebar-close-btn"><X className="h-5 w-5" /></button>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b bg-white/80 px-4 backdrop-blur-md dark:bg-slate-900/80 sm:px-6 no-print">
          <button className="rounded-md p-2 hover:bg-muted lg:hidden" onClick={() => setOpen(true)} data-testid="sidebar-toggle-btn"><Menu className="h-5 w-5" /></button>
          <div className="hidden lg:block text-sm text-muted-foreground">Business Finance & HPP Management System</div>
          <div className="flex items-center gap-2">
            <Link to="/" className="relative rounded-md p-2 hover:bg-muted" title="Notifikasi stok" data-testid="stock-alert-bell">
              <Bell className="h-4 w-4" />
              {alerts?.count > 0 && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-orange-500 px-1 text-[10px] font-bold text-white" data-testid="stock-alert-count">{alerts.count}</span>}
            </Link>
            <button onClick={toggleDark} className="rounded-md p-2 hover:bg-muted" data-testid="theme-toggle-btn">{dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</button>
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium" data-testid="header-user-name">{user?.name}</p>
              <p className="text-xs text-muted-foreground">{user?.role}</p>
            </div>
            <button onClick={async () => { await logout(); nav("/login"); }} className="rounded-md p-2 hover:bg-muted" title="Keluar" data-testid="logout-btn"><LogOut className="h-4 w-4" /></button>
          </div>
        </header>
        <main className="p-4 sm:p-6 lg:p-8"><Outlet /></main>
      </div>
    </div>
  );
}
