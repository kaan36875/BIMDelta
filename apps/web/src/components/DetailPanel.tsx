import { useDiffStore } from "../store/diff-store";
import { CHANGE_COLORS } from "../utils/colors";

export function DetailPanel() {
  const { diffResult, selectedElementId } = useDiffStore();

  if (!diffResult || !selectedElementId) {
    return (
      <div className="p-4 text-sm text-gray-400 italic">
        Select an element to view details
      </div>
    );
  }

  const el = diffResult.elements.find(
    (e) => e.global_id === selectedElementId,
  );
  if (!el) return null;

  return (
    <div className="p-4 space-y-4 overflow-auto text-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">
          {el.name ?? el.ifc_class}
        </h3>
        <span
          className="px-2 py-0.5 rounded text-xs font-medium"
          style={{
            backgroundColor: CHANGE_COLORS[el.change_type] + "22",
            color: CHANGE_COLORS[el.change_type],
          }}
        >
          {el.change_type}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <dt className="text-gray-500">GlobalId</dt>
        <dd className="font-mono">{el.global_id}</dd>
        <dt className="text-gray-500">Class</dt>
        <dd>{el.ifc_class}</dd>
        <dt className="text-gray-500">Storey</dt>
        <dd>{el.storey ?? "—"}</dd>
        {el.match_method && (
          <>
            <dt className="text-gray-500">Match</dt>
            <dd>
              {el.match_method}
              {el.matched_global_id && (
                <span className="text-gray-400 ml-1">
                  (v1: {el.matched_global_id})
                </span>
              )}
            </dd>
          </>
        )}
      </dl>

      {(el.geometry_changed ||
        el.placement_changed ||
        el.type_changed ||
        el.name_changed ||
        el.storey_changed) && (
        <div className="space-y-1">
          <h4 className="font-medium text-gray-700">Changes</h4>
          <ul className="text-xs space-y-0.5 text-gray-600">
            {el.geometry_changed && <li>Geometry changed</li>}
            {el.placement_changed && <li>Placement changed</li>}
            {el.type_changed && (
              <li>
                Type: {el.old_type_name} &rarr; {el.new_type_name}
              </li>
            )}
            {el.name_changed && (
              <li>
                Name: {el.old_name} &rarr; {el.name}
              </li>
            )}
            {el.storey_changed && (
              <li>
                Storey: {el.old_storey} &rarr; {el.storey}
              </li>
            )}
          </ul>
        </div>
      )}

      {(el.geometry_unknown || (el.ignored_property_changes ?? 0) > 0) && (
        <ul className="text-xs space-y-0.5 text-gray-400">
          {el.geometry_unknown && (
            <li>Geometry could not be evaluated, so it was not compared</li>
          )}
          {(el.ignored_property_changes ?? 0) > 0 && (
            <li>
              {el.ignored_property_changes} property{" "}
              {el.ignored_property_changes === 1 ? "difference" : "differences"} hidden as
              export noise
            </li>
          )}
        </ul>
      )}

      {el.property_changes.length > 0 && (
        <div className="space-y-1">
          <h4 className="font-medium text-gray-700">Property Changes</h4>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b">
                <th className="text-left py-1">Property</th>
                <th className="text-left py-1">Old</th>
                <th className="text-left py-1">New</th>
              </tr>
            </thead>
            <tbody>
              {el.property_changes.map((p, i) => (
                <tr key={i} className="border-b border-gray-100">
                  <td className="py-1">
                    <span className="text-gray-400">{p.pset_name}.</span>
                    {p.property_name}
                    <span className="text-gray-300 ml-1">({p.source})</span>
                  </td>
                  <td className="py-1 text-red-600">
                    {formatValue(p.old_value)}
                  </td>
                  <td className="py-1 text-green-600">
                    {formatValue(p.new_value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function formatValue(v: string | number | boolean | null): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4);
  return String(v);
}
