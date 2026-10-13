import { useEffect, useState } from "react";
import { fetchBlame, type BlameResult } from "../api/local";

const CHANGE_STYLE: Record<string, string> = {
  added: "text-green-700 bg-green-50",
  removed: "text-red-700 bg-red-50",
  modified: "text-amber-700 bg-amber-50",
  reidentified: "text-gray-600 bg-gray-100",
};

/** Commits that added, changed or removed one element, newest first. */
export function ElementHistory({
  path,
  globalId,
  rev,
}: {
  path: string;
  globalId: string;
  rev: string;
}) {
  const [state, setState] = useState<
    { key: string; result?: BlameResult; error?: string } | null
  >(null);
  const key = `${path}|${globalId}|${rev}`;

  useEffect(() => {
    let cancelled = false;
    fetchBlame(path, globalId, rev)
      .then((result) => !cancelled && setState({ key, result }))
      .catch((e) => !cancelled && setState({ key, error: e instanceof Error ? e.message : String(e) }));
    return () => {
      cancelled = true;
    };
  }, [key, path, globalId, rev]);

  if (!state || state.key !== key) {
    return <p className="text-xs text-gray-400">Reading history…</p>;
  }
  if (state.error) return <p className="text-xs text-red-600">{state.error}</p>;
  const result = state.result!;

  return (
    <ol className="space-y-2 text-xs">
      {result.events.map((ev) => (
        <li key={`${ev.sha}-${ev.change}`} className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className={`px-1.5 py-0.5 rounded font-medium ${CHANGE_STYLE[ev.change] ?? ""}`}>
              {ev.change}
            </span>
            <span className="font-mono text-gray-500">{ev.sha.slice(0, 7)}</span>
            <span className="text-gray-400">{ev.date.slice(0, 10)}</span>
          </div>
          <div className="text-gray-800">{ev.subject}</div>
          <div className="text-gray-500">{ev.author}</div>
          {ev.details.length > 0 && (
            <ul className="text-gray-600 list-disc pl-4">
              {ev.details.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
      {result.events.length === 0 && (
        <li className="text-gray-400">No changes in the commits scanned.</li>
      )}
      {result.present_before && (
        <li className="text-gray-400">Already present before the oldest commit scanned.</li>
      )}
    </ol>
  );
}
