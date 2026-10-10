import { useDiffStore } from "../store/diff-store";
import type { ChangeType } from "../types/diff";
import { CHANGE_COLORS, CHANGE_LABELS } from "../utils/colors";

const TYPES: ChangeType[] = ["added", "removed", "modified", "unchanged"];

export function ChangeSummary() {
  const { diffResult, filterChangeType, setFilterChangeType } = useDiffStore();
  if (!diffResult) return null;

  const s = diffResult.summary;
  const counts: Record<ChangeType, number> = {
    added: s.added,
    removed: s.removed,
    modified: s.modified,
    unchanged: s.unchanged,
  };

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
        Summary
      </h2>

      <div className="grid grid-cols-2 gap-2">
        {TYPES.map((ct) => (
          <button
            key={ct}
            onClick={() =>
              setFilterChangeType(filterChangeType === ct ? null : ct)
            }
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all
                        ${filterChangeType === ct ? "ring-2 ring-blue-500 bg-white shadow-sm" : "bg-gray-50 hover:bg-gray-100"}`}
          >
            <span
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: CHANGE_COLORS[ct] }}
            />
            <span className="font-medium text-gray-700">
              {CHANGE_LABELS[ct]}
            </span>
            <span className="ml-auto font-bold text-gray-900">
              {counts[ct]}
            </span>
          </button>
        ))}
      </div>

      <div className="text-xs text-gray-500 pt-1">
        {s.total_v1} elements in v1 &middot; {s.total_v2} in v2
      </div>

      {s.storey_elevation_changes.length > 0 && (
        <div className="mt-2 p-2 bg-amber-50 rounded text-xs text-amber-800">
          <strong>Storey elevation changes:</strong>
          {s.storey_elevation_changes.map((c) => (
            <div key={c.storey_name}>
              {c.storey_name}: {c.old_elevation.toFixed(3)}m &rarr;{" "}
              {c.new_elevation.toFixed(3)}m
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
