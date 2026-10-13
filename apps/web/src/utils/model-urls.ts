export interface ModelUrls {
  v1Url: string;
  v2Url: string;
}

/** The two model URLs from `?v1_url=…&v2_url=…`, if both are present. */
export function readModelUrls(search: string): ModelUrls | null {
  const params = new URLSearchParams(search);
  const v1Url = params.get("v1_url");
  const v2Url = params.get("v2_url");
  return v1Url && v2Url ? { v1Url, v2Url } : null;
}

export function clearModelUrls() {
  window.history.replaceState(null, "", window.location.pathname);
}
