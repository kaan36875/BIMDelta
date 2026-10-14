// API of `bimdelta serve`, which serves this app for a local Git repository.
import type { DiffResult } from "../types/diff";

declare global {
  interface Window {
    BIMDELTA_LOCAL?: boolean;
  }
}

export const WORKTREE = "worktree";

export const isLocalMode = () => window.BIMDELTA_LOCAL === true;

export interface RepoFile {
  path: string;
  worktree_changed: boolean;
}

export interface RepoInfo {
  name: string;
  head: string | null;
  version: string;
  files: RepoFile[];
}

export interface Commit {
  sha: string;
  author: string;
  date: string;
  subject: string;
}

export interface FileLog {
  path: string;
  commits: Commit[]; // newest first
  worktree_changed: boolean;
}

export interface BlameEvent {
  change: "added" | "modified" | "removed" | "reidentified";
  sha: string;
  author: string;
  date: string;
  subject: string;
  global_id: string;
  ifc_class: string | null;
  name: string | null;
  details: string[];
}

export interface BlameResult {
  global_id: string;
  path: string;
  commits_scanned: number;
  truncated: boolean;
  events: BlameEvent[]; // newest first
  present_before: boolean;
}

async function get<T>(endpoint: string, params: Record<string, string>): Promise<T> {
  const resp = await fetch(`/api/local/${endpoint}?${new URLSearchParams(params)}`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export const fetchRepoInfo = () => get<RepoInfo>("info", {});
export const fetchLog = (path: string) => get<FileLog>("log", { path });
export const fetchLocalDiff = (path: string, base: string, head: string) =>
  get<DiffResult>("diff", { path, base, head });
export const fetchBlame = (path: string, globalId: string, rev: string) =>
  get<BlameResult>("blame", { path, global_id: globalId, rev });

export async function fetchLocalModel(path: string, rev: string): Promise<File> {
  const resp = await fetch(`/api/local/model?${new URLSearchParams({ path, rev })}`);
  if (!resp.ok) throw new Error(`Could not load ${path} at ${revLabel(rev)}`);
  const name = path.split("/").pop() || "model.ifc";
  return new File([await resp.blob()], name);
}

export const revLabel = (rev: string) => (rev === WORKTREE ? "working copy" : rev.slice(0, 7));
