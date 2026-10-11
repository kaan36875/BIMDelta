import { useMemo } from "react";
import { useDiffStore, useFilteredElements } from "../store/diff-store";
import { CHANGE_COLORS } from "../utils/colors";

export function ChangeTable() {
  const {
    diffResult,
    selectedElementId,
    selectElement,
    filterClass,
    setFilterClass,
    filterStorey,
    setFilterStorey,
    searchText,
    setSearchText,
  } = useDiffStore();
  const filtered = useFilteredElements();

  const classes = useMemo(() => {
    if (!diffResult) return [];
    return [
      ...new Set(diffResult.elements.map((e) => e.ifc_class)),
    ].sort();
  }, [diffResult]);

  const storeys = useMemo(() => {
    if (!diffResult) return [];
    return [
      ...new Set(
        diffResult.elements.map((e) => e.storey).filter(Boolean) as string[],
      ),
    ].sort();
  }, [diffResult]);

  if (!diffResult) return null;

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-2 p-2 bg-gray-50 border-b text-sm">
        <input
          type="text"
          placeholder="Search..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="px-2 py-1 border rounded text-sm w-48"
        />
        <select
          value={filterClass ?? ""}
          onChange={(e) => setFilterClass(e.target.value || null)}
          className="px-2 py-1 border rounded text-sm"
        >
          <option value="">All classes</option>
          {classes.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={filterStorey ?? ""}
          onChange={(e) => setFilterStorey(e.target.value || null)}
          className="px-2 py-1 border rounded text-sm"
        >
          <option value="">All storeys</option>
          {storeys.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <span className="ml-auto text-gray-500 py-1">
          {filtered.length} elements
        </span>
      </div>

      <div className="overflow-auto flex-1">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white border-b">
            <tr className="text-left text-gray-500">
              <th className="px-3 py-2 w-8"></th>
              <th className="px-3 py-2">Class</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Storey</th>
              <th className="px-3 py-2">Change</th>
              <th className="px-3 py-2">Details</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((el) => (
              <tr
                key={el.global_id}
                onClick={() => selectElement(el.global_id)}
                className={`border-b cursor-pointer transition-colors
                  ${selectedElementId === el.global_id ? "bg-blue-50" : "hover:bg-gray-50"}`}
              >
                <td className="px-3 py-2">
                  <span
                    className="inline-block w-3 h-3 rounded-full"
                    style={{
                      backgroundColor: CHANGE_COLORS[el.change_type],
                    }}
                  />
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {el.ifc_class}
                </td>
                <td className="px-3 py-2">{el.name ?? "—"}</td>
                <td className="px-3 py-2 text-gray-500">
                  {el.storey ?? "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className="inline-block px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      backgroundColor: CHANGE_COLORS[el.change_type] + "22",
                      color: CHANGE_COLORS[el.change_type],
                    }}
                  >
                    {el.change_type}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs text-gray-500">
                  {summaryLine(el)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function summaryLine(
  el: ReturnType<typeof useFilteredElements>[number],
): string {
  const parts: string[] = [];
  if (el.property_changes.length)
    parts.push(`${el.property_changes.length} props`);
  if (el.geometry_changed) parts.push("geom");
  if (el.placement_changed) parts.push("placement");
  if (el.type_changed) parts.push("type");
  if (el.name_changed) parts.push("name");
  if (el.storey_changed) parts.push("storey");
  if (el.geometry_unknown) parts.push("geometry not compared");
  if (el.match_method === "fallback") parts.push("fallback match");
  return parts.join(", ");
}
