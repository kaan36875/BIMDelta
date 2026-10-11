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

      <FilteredNote />

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

const MAX_PSETS_SHOWN = 5;

function FilteredNote() {
  const s = useDiffStore((state) => state.diffResult?.summary);
  if (!s) return null;

  const ignored = s.noise?.ignored_property_changes ?? 0;
  const oneSided = s.noise?.one_sided_psets ?? [];
  const geometryUnknown = s.geometry_unknown ?? 0;
  if (!ignored && !oneSided.length && !geometryUnknown) return null;

  return (
    <div className="p-2 bg-gray-50 rounded text-xs text-gray-600 space-y-1">
      {ignored > 0 && (
        <div>
          {ignored} property {ignored === 1 ? "difference" : "differences"} hidden as export
          noise
        </div>
      )}
      {oneSided.length > 0 && (
        <div>
          Property sets in only one file (not counted as changes):
          <ul className="ml-3 list-disc">
            {oneSided.slice(0, MAX_PSETS_SHOWN).map((p) => (
              <li key={`${p.only_in}-${p.pset_name}`}>
                {p.pset_name}{" "}
                <span className="text-gray-400">
                  ({p.only_in}, {p.element_count} elements)
                </span>
              </li>
            ))}
          </ul>
          {oneSided.length > MAX_PSETS_SHOWN && (
            <div className="text-gray-400">
              and {oneSided.length - MAX_PSETS_SHOWN} more
            </div>
          )}
        </div>
      )}
      {geometryUnknown > 0 && (
        <div>
          {geometryUnknown} {geometryUnknown === 1 ? "element" : "elements"}: geometry could not
          be evaluated, so it was not compared
        </div>
      )}
    </div>
  );
}
