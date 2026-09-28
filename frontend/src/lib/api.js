import axios from "axios";

export const BACKEND = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND}/api`;
export const api = axios.create({ baseURL: API, withCredentials: true });

api.interceptors.request.use((c) => {
  const t = localStorage.getItem("token");
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || "Terjadi kesalahan";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x?.msg ? `${(x.loc || []).slice(-1)[0]}: ${x.msg}` : JSON.stringify(x))).join("; ");
  return d.msg || String(d);
}

export const fileUrl = (url) => (url ? (url.startsWith("http") ? url : `${BACKEND}${url}?auth=${localStorage.getItem("token") || ""}`) : "");
