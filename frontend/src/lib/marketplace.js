import { useApi } from "./hooks";
import { cn } from "./utils";

export const CHANNELS = ["Shopee", "TikTok Shop", "Tokopedia", "Website"];
export const STATUSES = ["Pending", "Diproses", "Dikirim", "Selesai", "Dibatalkan", "Dikembalikan", "Refund"];
export const channelOpts = CHANNELS.map((c) => ({ value: c, label: c }));
export const statusOpts = STATUSES.map((s) => ({ value: s, label: s }));

const STATUS_CLS = {
  Pending: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300", Diproses: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300", Dikirim: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  Selesai: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300", Dibatalkan: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300", Dikembalikan: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  Refund: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300", Matched: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300", Difference: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300", Refunded: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
};
export const StatusBadge = ({ status }) => <span className={cn("inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold", STATUS_CLS[status] || "badge-muted")} data-testid={`status-badge-${status}`}>{status}</span>;

const CH_CLS = { Shopee: "bg-orange-500", "TikTok Shop": "bg-slate-900 dark:bg-slate-200 dark:text-slate-900", Tokopedia: "bg-emerald-600", Website: "bg-teal-600" };
export const ChannelBadge = ({ channel }) => <span className={cn("inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold text-white", CH_CLS[channel] || "bg-slate-500")}>{channel}</span>;

export const useMarketplaceMeta = () => useApi("/marketplace/meta");
export const useProducts = () => useApi("/products");
export const productOpts = (products) => (products || []).map((p) => ({ value: p.id, label: `${p.name}${p.sku ? ` (${p.sku})` : ""}` }));
