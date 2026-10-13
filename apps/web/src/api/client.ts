import type { DiffResult } from "../types/diff";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Hosts the URL mode opens models from; the server enforces the same list.
export const ALLOWED_MODEL_HOSTS = [
  "raw.githubusercontent.com",
  "media.githubusercontent.com",
];

const LFS_POINTER = "version https://git-lfs.github.com/spec/v1";

async function readError(resp: Response): Promise<Error> {
  const err = await resp.json().catch(() => ({ detail: resp.statusText }));
  return new Error(err.detail || `HTTP ${resp.status}`);
}

export async function fetchDiff(v1: File, v2: File): Promise<DiffResult> {
  const form = new FormData();
  form.append("v1", v1);
  form.append("v2", v2);

  const resp = await fetch(`${API_BASE}/api/diff`, { method: "POST", body: form });
  if (!resp.ok) throw await readError(resp);
  return resp.json();
}

export async function fetchDiffFromUrls(v1Url: string, v2Url: string): Promise<DiffResult> {
  const resp = await fetch(`${API_BASE}/api/diff/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ v1_url: v1Url, v2_url: v2Url }),
  });
  if (!resp.ok) throw await readError(resp);
  return resp.json();
}

export function checkModelUrl(url: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`Not a valid URL: ${url}`);
  }
  if (parsed.protocol !== "https:" || !ALLOWED_MODEL_HOSTS.includes(parsed.hostname)) {
    throw new Error(
      `Models can only be opened from ${ALLOWED_MODEL_HOSTS.join(" or ")}; got ${parsed.host}`,
    );
  }
  return parsed;
}

/** "house.ifc @ 1a2b3c4" for a raw GitHub URL (/owner/repo/<sha>/path), else the file name. */
export function modelLabel(url: string): string {
  const parts = new URL(url).pathname.split("/").filter(Boolean);
  if (parts[0] === "media") parts.shift();
  const name = decodeURIComponent(parts[parts.length - 1] || "model.ifc");
  const ref = parts[2];
  return ref && /^[0-9a-f]{7,40}$/i.test(ref) ? `${name} @ ${ref.slice(0, 7)}` : name;
}

/** Download a model for the 3D view. A Git LFS pointer is swapped for its content. */
export async function downloadModel(url: string): Promise<File> {
  const parsed = checkModelUrl(url);
  const resp = await fetch(parsed.href);
  if (!resp.ok) {
    throw new Error(
      `Could not download ${modelLabel(url)} (HTTP ${resp.status}). The repository may be ` +
        "private or the file may not exist at that commit; the viewer can only open files " +
        "from public repositories.",
    );
  }
  const blob = await resp.blob();
  if (blob.size < 1024 && (await blob.text()).startsWith(LFS_POINTER)) {
    if (parsed.hostname !== "raw.githubusercontent.com") {
      throw new Error(`${modelLabel(url)} is a Git LFS pointer, not a model`);
    }
    return downloadModel(`https://media.githubusercontent.com/media${parsed.pathname}`);
  }
  const name = decodeURIComponent(parsed.pathname.split("/").pop() || "model.ifc");
  return new File([blob], name);
}
