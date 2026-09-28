import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "./api";

export function useApi(url, deps = [], { enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!enabled || !url) return;
    setLoading(true);
    setData(null);
    try {
      const { data } = await api.get(url);
      setData(data);
    } catch (e) { toast.error(errMsg(e)); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, enabled, ...deps]);
  useEffect(() => { reload(); }, [reload]);
  return { data, loading, reload, setData };
}

export const qs = (obj) => {
  const p = Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(v)}`);
  return p.length ? `?${p.join("&")}` : "";
};
