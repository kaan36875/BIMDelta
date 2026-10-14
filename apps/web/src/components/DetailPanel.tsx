import { useState, type ReactNode } from "react";
import { useDiffStore } from "../store/diff-store";
import {
  GROUP_LABELS,
  groupChanges,
  type ChangeGroup,
  type ChangeRow,
} from "../utils/change-groups";
import { CHANGE_COLORS } from "../utils/colors";

const GROUPS: ChangeGroup[] = ["geometry", "type", "material", "properties"];

export function DetailPanel({ history }: { history?: (globalId: string) => ReactNode }) {
  const { diffResult, selectedElementId } = useDiffStore();
  const [tab, setTab] = useState<ChangeGroup | "history" | null>(null);

  if (!diffResult || !selectedElementId) {
    return (
      <div className="p-4 text-sm text-gray-400 italic">
        Select an element to view details
      </div>
    );
  }

  const el = diffResult.elements.find((e) => e.global_id === selectedElementId);
  if (!el) return null;

  const groups = groupChanges(el);
  const withChanges = GROUPS.filter((g) => groups[g].length > 0);
  const tabs: (ChangeGroup | "history")[] = [...GROUPS, ...(history ? ["history" as const] : [])];
  // Default to the first tab with something in it.
  const active = tab && (tab === "history" || groups[tab].length > 0 || withChanges.length === 0)
    ? tab
    : (withChanges[0] ?? (history ? "history" : "geometry"));

  return (
    <div className="p-4 space-y-4 overflow-auto text-sm">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold text-gray-800 truncate">{el.name ?? el.ifc_class}</h3>
        <span
          className="px-2 py-0.5 rounded text-xs font-medium shrink-0"
          style={{
            backgroundColor: CHANGE_COLORS[el.change_type] + "22",
            color: CHANGE_COLORS[el.change_type],
          }}
        >
          {el.change_type}
        </span>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        <dt className="text-gray-500">GlobalId</dt>
        <dd className="font-mono break-all">{el.global_id}</dd>
        <dt className="text-gray-500">Class</dt>
        <dd>{el.ifc_class}</dd>
        <dt className="text-gray-500">Storey</dt>
        <dd>{el.storey ?? "—"}</dd>
        {el.match_method && (
          <>
            <dt className="text-gray-500">Match</dt>
            <dd>
              {el.match_method.replace("_", " ")}
              {el.matched_global_id && (
                <span className="text-gray-400 ml-1 break-all">(v1: {el.matched_global_id})</span>
              )}
            </dd>
          </>
        )}
      </dl>

      {el.change_type === "modified" || history ? (
        <div>
          <div className="flex flex-wrap border-b text-xs" role="tablist">
            {tabs.map((t) => {
              const count = t === "history" ? 0 : groups[t].length;
              const disabled = t !== "history" && count === 0;
              return (
                <button
                  key={t}
                  role="tab"
                  aria-selected={active === t}
                  disabled={disabled}
                  onClick={() => setTab(t)}
                  className={`px-1.5 py-1.5 -mb-px border-b-2 transition-colors ${
                    active === t
                      ? "border-blue-600 text-blue-700 font-medium"
                      : "border-transparent text-gray-500 hover:text-gray-800"
                  } disabled:text-gray-300 disabled:hover:text-gray-300`}
                >
                  {t === "history" ? "History" : GROUP_LABELS[t]}
                  {count > 0 && <span className="ml-1 text-gray-400">{count}</span>}
                </button>
              );
            })}
          </div>
          <div className="pt-2">
            {active === "history" && history ? (
              history(el.global_id)
            ) : groups[active as ChangeGroup].length > 0 ? (
              <ChangeTable rows={groups[active as ChangeGroup]} />
            ) : (
              <p className="text-xs text-gray-400 italic">No changes here.</p>
            )}
          </div>
        </div>
      ) : null}

      {(el.geometry_unknown || (el.ignored_property_changes ?? 0) > 0) && (
        <ul className="text-xs space-y-0.5 text-gray-400">
          {el.geometry_unknown && <li>Geometry could not be evaluated, so it was not compared</li>}
          {(el.ignored_property_changes ?? 0) > 0 && (
            <li>
              {el.ignored_property_changes} property{" "}
              {el.ignored_property_changes === 1 ? "difference" : "differences"} hidden as export
              noise
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

function ChangeTable({ rows }: { rows: ChangeRow[] }) {
  return (
    <table className="w-full text-xs table-fixed">
      <thead>
        <tr className="text-gray-500 border-b">
          <th className="text-left py-1 w-2/5 font-normal">&nbsp;</th>
          <th className="text-left py-1 font-normal">Old</th>
          <th className="text-left py-1 font-normal">New</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-gray-100 align-top">
            <td className="py-1 pr-2 break-words">
              {r.label}
              {r.detail && <div className="text-gray-400">{r.detail}</div>}
            </td>
            <td className="py-1 pr-2 text-red-600 break-words">{r.old}</td>
            <td className="py-1 text-green-600 break-words">{r.new}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
