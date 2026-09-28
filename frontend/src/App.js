import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth } from "./lib/auth";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import { Materials, Products, Suppliers, Categories, Units } from "./pages/MasterData";
import Recipes from "./pages/Recipes";
import HppCalculator from "./pages/HppCalculator";
import Production from "./pages/Production";
import Stock from "./pages/Stock";
import { Purchases, Sales, Expenses } from "./pages/Transactions";
import { Cash, ProfitLoss, CashFlow, Bep } from "./pages/Finance";
import Reports from "./pages/Reports";
import SettingsPage from "./pages/Settings";
import MarketplaceDashboard from "./pages/marketplace/MarketplaceDashboard";
import Orders from "./pages/marketplace/Orders";
import Packaging from "./pages/marketplace/Packaging";
import ChannelFees from "./pages/marketplace/ChannelFees";
import MarketplaceImport from "./pages/marketplace/Import";
import SettlementsPage from "./pages/marketplace/Settlements";
import MarketplaceReports from "./pages/marketplace/MarketplaceReports";

if (localStorage.getItem("theme") === "dark") document.documentElement.classList.add("dark");

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Memuat...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><Layout /></Protected>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/bahan" element={<Materials />} />
            <Route path="/produk" element={<Products />} />
            <Route path="/supplier" element={<Suppliers />} />
            <Route path="/kategori" element={<Categories />} />
            <Route path="/satuan" element={<Units />} />
            <Route path="/resep" element={<Recipes />} />
            <Route path="/hpp" element={<HppCalculator />} />
            <Route path="/produksi" element={<Production />} />
            <Route path="/stok" element={<Stock />} />
            <Route path="/pembelian" element={<Purchases />} />
            <Route path="/penjualan" element={<Sales />} />
            <Route path="/pengeluaran" element={<Expenses />} />
            <Route path="/kas" element={<Cash />} />
            <Route path="/laba-rugi" element={<ProfitLoss />} />
            <Route path="/cash-flow" element={<CashFlow />} />
            <Route path="/bep" element={<Bep />} />
            <Route path="/laporan/:type" element={<Reports />} />
            <Route path="/pengaturan" element={<SettingsPage />} />
            <Route path="/marketplace" element={<MarketplaceDashboard />} />
            <Route path="/marketplace/order" element={<Orders />} />
            <Route path="/marketplace/packaging" element={<Packaging />} />
            <Route path="/marketplace/biaya" element={<ChannelFees />} />
            <Route path="/marketplace/import" element={<MarketplaceImport />} />
            <Route path="/marketplace/settlement" element={<SettlementsPage />} />
            <Route path="/marketplace/laporan/:type" element={<MarketplaceReports />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </AuthProvider>
  );
}

export default App;
