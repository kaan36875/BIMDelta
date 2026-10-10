import { useCallback, useEffect, useRef, useState } from "react";
import { useDiffStore } from "../store/diff-store";
import { executeQuery, type QueryResult } from "../utils/query-engine";

const EXAMPLE_QUERIES = [
  "Which walls were modified?",
  "Show added doors",
  "What changed on floor 1?",
  "Removed columns",
  "Elements with geometry changes",
];

export function QueryBar() {
  const { diffResult, selectElement } = useDiffStore();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [showExamples, setShowExamples] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleQuery = useCallback(
    (q: string) => {
      if (!diffResult || !q.trim()) {
        setResult(null);
        return;
      }
      const r = executeQuery(q, diffResult.elements);
      setResult(r);
    },
    [diffResult],
  );

  useEffect(() => {
    const timer = setTimeout(() => handleQuery(query), 200);
    return () => clearTimeout(timer);
  }, [query, handleQuery]);

  const handleClickElement = (globalId: string) => {
    selectElement(globalId);
  };

  if (!diffResult) return null;

  const matchedElements = result?.matchedIds
    ? diffResult.elements.filter((el) => result.matchedIds.has(el.global_id))
    : [];

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => !query && setShowExamples(true)}
            onBlur={() => setTimeout(() => setShowExamples(false), 200)}
            placeholder='Ask about changes... (e.g. "which walls were modified?")'
            className="w-full px-3 py-2 pl-9 border rounded-lg text-sm bg-gray-50
                       focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20
                       focus:border-blue-400 transition-all"
          />
          <svg
            className="absolute left-3 top-2.5 w-4 h-4 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          {query && (
            <button
              onClick={() => {
                setQuery("");
                setResult(null);
              }}
              className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        {result && result.matchedIds.size > 0 && (
          <span className="text-xs text-gray-500 whitespace-nowrap">
            {result.matchedIds.size} result{result.matchedIds.size !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {showExamples && !query && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg z-10 py-1">
          <div className="px-3 py-1.5 text-xs text-gray-400">Try asking:</div>
          {EXAMPLE_QUERIES.map((eq) => (
            <button
              key={eq}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                setQuery(eq);
                setShowExamples(false);
                inputRef.current?.focus();
              }}
              className="w-full text-left px-3 py-1.5 text-sm text-gray-700
                         hover:bg-blue-50 hover:text-blue-700 transition-colors"
            >
              {eq}
            </button>
          ))}
        </div>
      )}

      {result && query && (
        <div className="mt-2 space-y-2">
          <p className="text-sm text-gray-700">{result.answer}</p>

          {matchedElements.length > 0 && matchedElements.length <= 20 && (
            <div className="flex flex-wrap gap-1.5">
              {matchedElements.map((el) => (
                <button
                  key={el.global_id}
                  onClick={() => handleClickElement(el.global_id)}
                  className="px-2 py-1 text-xs rounded-md border bg-white
                             hover:bg-blue-50 hover:border-blue-300 transition-colors
                             truncate max-w-[200px]"
                  title={`${el.ifc_class} — ${el.change_type}`}
                >
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-1.5"
                    style={{ backgroundColor: changeColor(el.change_type) }}
                  />
                  {el.name || el.ifc_class}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function changeColor(ct: string): string {
  const map: Record<string, string> = {
    added: "#22c55e",
    removed: "#ef4444",
    modified: "#f59e0b",
    unchanged: "#9ca3af",
  };
  return map[ct] ?? "#9ca3af";
}
