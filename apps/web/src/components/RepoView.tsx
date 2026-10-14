import { useCallback, useEffect, useRef, useState } from "react";
import {
  WORKTREE,
  fetchLocalDiff,
  fetchLocalModel,
  fetchLog,
  fetchRepoInfo,
  revLabel,
  type FileLog,
  type RepoInfo,
} from "../api/local";
import { useDiffStore } from "../store/diff-store";
import { ElementHistory } from "./ElementHistory";
import { MainView } from "./MainView";
import { Timeline, type Selection } from "./Timeline";

/** The viewer when served by `bimdelta serve`: pick an IFC file and two of its revisions. */
export function RepoView() {
  const { diffResult, setDiffResult, setFiles } = useDiffStore();
  const [info, setInfo] = useState<RepoInfo | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [log, setLog] = useState<FileLog | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);

  useEffect(() => {
    fetchRepoInfo()
      .then((i) => {
        setInfo(i);
        const first = i.files.find((f) => f.worktree_changed) ?? i.files[0];
        if (first) setPath(first.path);
      })
      .catch((e) => setError(String(e instanceof Error ? e.message : e)));
  }, []);

  const load = useCallback(
    async (p: string, s: Selection) => {
      const id = ++request.current;
      setBusy(true);
      setError(null);
      try {
        const [v1, v2, result] = await Promise.all([
          fetchLocalModel(p, s.base),
          fetchLocalModel(p, s.head),
          fetchLocalDiff(p, s.base, s.head),
        ]);
        if (id !== request.current) return;
        const name = p.split("/").pop() ?? p;
        setFiles(v1, v2);
        setDiffResult({
          ...result,
          v1_filename: `${name} @ ${revLabel(s.base)}`,
          v2_filename: `${name} @ ${revLabel(s.head)}`,
        });
      } catch (e) {
        if (id === request.current) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (id === request.current) setBusy(false);
      }
    },
    [setDiffResult, setFiles],
  );

  const select = useCallback(
    (p: string, s: Selection) => {
      setSelection(s);
      load(p, s);
    },
    [load],
  );

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    fetchLog(path)
      .then((l) => {
        if (cancelled) return;
        setLog(l);
        const newest = l.commits[0]?.sha;
        if (l.worktree_changed && newest) select(path, { base: newest, head: WORKTREE });
        else if (l.commits.length >= 2) select(path, { base: l.commits[1].sha, head: newest });
        else if (newest) select(path, { base: newest, head: newest });
        else if (l.worktree_changed) setError(`${path} has not been committed yet.`);
      })
      .catch((e) => !cancelled && setError(String(e instanceof Error ? e.message : e)));
    return () => {
      cancelled = true;
    };
  }, [path, select]);


  const toolbar = (
    <div className="flex items-center gap-4">
      <span className="text-xs font-medium text-gray-700 shrink-0">{info?.name}</span>
      {info && info.files.length > 1 && (
        <select
          value={path ?? ""}
          onChange={(e) => {
            setLog(null);
            setPath(e.target.value);
          }}
          className="text-xs border rounded px-1 py-0.5"
        >
          {info.files.map((f) => (
            <option key={f.path} value={f.path}>
              {f.path}
              {f.worktree_changed ? " •" : ""}
            </option>
          ))}
        </select>
      )}
      <div className="min-w-0 flex-1">
        {log && <Timeline
            log={log}
            selection={selection}
            onSelect={(s) => path && select(path, s)}
            busy={busy}
          />}
      </div>
      {busy && <span className="text-xs text-gray-400 shrink-0">Comparing…</span>}
      {error && <span className="text-xs text-red-600 shrink-0 max-w-sm truncate" title={error}>{error}</span>}
    </div>
  );

  if (!diffResult) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-3xl font-bold text-gray-900">BIMDelta</h1>
        {info && info.files.length === 0 ? (
          <p className="text-gray-500">No IFC files in {info.name}.</p>
        ) : error ? (
          <p className="text-red-600 text-sm max-w-xl text-center">{error}</p>
        ) : (
          <p className="text-gray-500">Loading {path ?? "repository"}…</p>
        )}
      </div>
    );
  }

  const historyRev = selection && selection.head !== WORKTREE ? selection.head : "HEAD";
  return (
    <MainView
      onHome={() => window.location.reload()}
      toolbar={toolbar}
      history={
        path ? (gid) => <ElementHistory path={path} globalId={gid} rev={historyRev} /> : undefined
      }
    />
  );
}
