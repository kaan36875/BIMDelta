import type { DiffResult } from "../types/diff";

const API_BASE = import.meta.env.VITE_API_URL || "";

export async function fetchDiff(v1: File, v2: File): Promise<DiffResult> {
  const form = new FormData();
  form.append("v1", v1);
  form.append("v2", v2);

  const resp = await fetch(`${API_BASE}/api/diff`, { method: "POST", body: form });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  return resp.json();
}
