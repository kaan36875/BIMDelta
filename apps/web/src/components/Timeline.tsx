import { useEffect } from "react";
import { WORKTREE, type FileLog } from "../api/local";

export interface Selection {
  base: string;
  head: string;
}

interface Point {
  rev: string;
  label: string;
  title: string;
}

/** Revisions of one file, oldest on the left. Click a point to compare it with the one
 * before; shift-click to choose the base. Left and right arrows step through history. */
export function Timeline({
  log,
  selection,
  onSelect,
  busy,
}: {
  log: FileLog;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
  busy: boolean;
}) {
  const points: Point[] = [...log.commits].reverse().map((c) => ({
    rev: c.sha,
    label: c.sha.slice(0, 7),
    title: `${c.sha.slice(0, 7)} · ${c.author} · ${c.date.slice(0, 10)}\n${c.subject}`,
  }));
  if (log.worktree_changed) {
    points.push({ rev: WORKTREE, label: "working copy", title: "Uncommitted changes" });
  }

  const headIndex = points.findIndex((p) => p.rev === selection?.head);
  const baseIndex = points.findIndex((p) => p.rev === selection?.base);

  const selectHead = (i: number) => {
    if (i < 0 || i >= points.length) return;
    const base = points[Math.max(0, i - 1)].rev;
    onSelect({ base, head: points[i].rev });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (busy || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowLeft" && headIndex > 0) selectHead(headIndex - 1);
      if (e.key === "ArrowRight" && headIndex < points.length - 1) selectHead(headIndex + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (points.length === 0) {
    return <div className="text-xs text-gray-400">This file has no commits yet.</div>;
  }

  return (
    <div className="flex items-center gap-0 overflow-x-auto py-1" aria-label="Revisions">
      {points.map((p, i) => {
        const isHead = i === headIndex;
        const isBase = i === baseIndex && !isHead;
        const inRange = baseIndex >= 0 && headIndex >= 0 && i > baseIndex && i < headIndex;
        return (
          <div key={p.rev} className="flex items-center shrink-0">
            {i > 0 && (
              <div
                className={`h-0.5 w-8 ${
                  inRange || (i === headIndex && baseIndex < headIndex) ? "bg-blue-400" : "bg-gray-200"
                }`}
              />
            )}
            <button
              title={p.title}
              disabled={busy}
              onClick={(e) => {
                if (e.shiftKey && headIndex >= 0 && i !== headIndex) {
                  onSelect({ base: p.rev, head: points[headIndex].rev });
                } else {
                  selectHead(i);
                }
              }}
              className="flex flex-col items-center gap-0.5 px-1 group disabled:cursor-wait"
            >
              <span
                className={`block rounded-full border-2 transition-all ${
                  isHead
                    ? "w-4 h-4 bg-blue-600 border-blue-600"
                    : isBase
                      ? "w-3.5 h-3.5 bg-white border-blue-600"
                      : "w-3 h-3 bg-white border-gray-300 group-hover:border-gray-500"
                } ${p.rev === WORKTREE ? "border-dashed" : ""}`}
              />
              <span
                className={`text-[10px] font-mono ${
                  isHead || isBase ? "text-blue-700" : "text-gray-400"
                }`}
              >
                {p.label}
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
