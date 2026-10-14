import { useMemo, useState } from "react";
import { useDiffStore } from "../store/diff-store";
import type { QuantityDeltaRow, QuantityTotals } from "../types/diff";

type Pivot = "class" | "material" | "storey";
type Measure = keyof QuantityTotals;

const PIVOTS: { key: Pivot; label: string }[] = [
  { key: "class", label: "Class" },
  { key: "material", label: "Material" },
  { key: "storey", label: "Storey" },
];

const MEASURES: { key: Measure; label: string; digits: number }[] = [
  { key: "count", label: "Count", digits: 0 },
  { key: "length", label: "Length m", digits: 2 },
  { key: "area", label: "Area m²", digits: 2 },
  { key: "volume", label: "Volume m³", digits: 2 },
  { key: "weight", label: "Weight kg", digits: 0 },
];

// Changes smaller than this are rounding, not a change.
const EPSILON = 0.005;

function changed(row: QuantityDeltaRow): boolean {
  return MEASURES.some((m) => Math.abs(row.delta[m.key]) >= (m.key === "weight" ? 0.5 : EPSILON));
}

function format(value: number, digits: number, signed = false): string {
  const text = value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return signed && value > 0 ? `+${text}` : text;
}

/** Quantity take-off of both versions, pivoted by class, material or storey. */
export function QuantitiesTable({ onShowElements }: { onShowElements: () => void }) {
  const report = useDiffStore((s) => s.diffResult?.quantities);
  const setFilterClass = useDiffStore((s) => s.setFilterClass);
  const setFilterStorey = useDiffStore((s) => s.setFilterStorey);
  const [pivot, setPivot] = useState<Pivot>("material");
  const [changedOnly, setChangedOnly] = useState(true);

  const rows = useMemo(() => {
    if (!report) return [];
    const all = report[`by_${pivot}`];
    return changedOnly ? all.filter(changed) : all;
  }, [report, pivot, changedOnly]);

  if (!report) {
    return (
      <div className="p-4 text-sm text-gray-500">
        No quantity take-off in this result. It needs a diff from bimdelta 0.7 or newer.
      </div>
    );
  }

  const columns = MEASURES.filter(
    (m) =>
      m.key === "count" ||
      [...report[`by_${pivot}`], report.total].some((r) => r.v1[m.key] || r.v2[m.key]),
  );
  // Only worth saying when one version has no quantity sets at all (exported without base
  // quantities): the change is then that version's whole take-off.
  const t = report.total;
  const noneBefore = t.v1.count > 0 && report.v1_without_quantities === t.v1.count;
  const noneAfter = t.v2.count > 0 && report.v2_without_quantities === t.v2.count;
  const coverage =
    noneBefore !== noneAfter
      ? `v${noneBefore ? 1 : 2} has no quantity sets, so the change is its whole take-off. Export base quantities for both versions.`
      : null;
  const clickable = pivot !== "material";

  function show(group: string) {
    if (pivot === "class") setFilterClass(group);
    else if (pivot === "storey") setFilterStorey(group === "(no storey)" ? null : group);
    onShowElements();
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 p-2 bg-gray-50 border-b text-sm">
        <div className="flex rounded border overflow-hidden">
          {PIVOTS.map((p) => (
            <button
              key={p.key}
              onClick={() => setPivot(p.key)}
              className={`px-2 py-1 ${pivot === p.key ? "bg-blue-600 text-white" : "bg-white hover:bg-gray-100"}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-gray-600">
          <input
            type="checkbox"
            checked={changedOnly}
            onChange={(e) => setChangedOnly(e.target.checked)}
          />
          Changed only
        </label>
        {coverage && <span className="text-xs text-amber-700">{coverage}</span>}
        {pivot === "material" && (
          <span className="ml-auto text-xs text-gray-400">
            Volume and weight are split by layer; count, length and area count each material
            in full
          </span>
        )}
      </div>

      <div className="overflow-auto flex-1">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white border-b">
            <tr className="text-gray-500">
              <th className="px-3 py-2 text-left">{PIVOTS.find((p) => p.key === pivot)?.label}</th>
              {columns.map((m) => (
                <th key={m.key} className="px-3 py-2 text-right" colSpan={2}>
                  {m.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[report.total, ...rows].map((row, i) => (
              <tr
                key={i === 0 ? "__total__" : `g:${row.group}`}
                onClick={i > 0 && clickable ? () => show(row.group) : undefined}
                className={`border-b ${i === 0 ? "font-semibold bg-gray-50" : ""} ${
                  i > 0 && clickable ? "cursor-pointer hover:bg-gray-50" : ""
                }`}
              >
                <td className="px-3 py-1.5">{i === 0 ? "Total" : row.group}</td>
                {columns.map((m) => {
                  const delta = row.delta[m.key];
                  const tone =
                    Math.abs(delta) < EPSILON
                      ? "text-gray-300"
                      : delta > 0
                        ? "text-green-700"
                        : "text-red-700";
                  return [
                    <td key={m.key} className="px-2 py-1.5 text-right tabular-nums">
                      {format(row.v2[m.key], m.digits)}
                    </td>,
                    <td key={`${m.key}-d`} className={`pr-3 py-1.5 text-right tabular-nums ${tone}`}>
                      {format(delta, m.digits, true)}
                    </td>,
                  ];
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="p-4 text-sm text-gray-500">No quantity changed.</div>
        )}
      </div>
    </div>
  );
}
