import type { DiffResult, ElementDiff } from "../types/diff";

export function exportCsv(elements: ElementDiff[]): void {
  const headers = [
    "GlobalId",
    "IFC Class",
    "Name",
    "Storey",
    "Change Type",
    "Match Method",
    "Geometry Changed",
    "Placement Changed",
    "Property Changes",
  ];

  const rows = elements.map((el) => [
    el.global_id,
    el.ifc_class,
    el.name ?? "",
    el.storey ?? "",
    el.change_type,
    el.match_method ?? "",
    el.geometry_changed ? "Yes" : "No",
    el.placement_changed ? "Yes" : "No",
    el.property_changes
      .map(
        (p) =>
          `${p.pset_name}.${p.property_name}: ${fmtVal(p.old_value)} → ${fmtVal(p.new_value)}`,
      )
      .join("; "),
  ]);

  const csv =
    headers.join(",") +
    "\n" +
    rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");

  download(csv, "bimdelta-changes.csv", "text/csv");
}

export function exportHtmlReport(result: DiffResult): void {
  const s = result.summary;
  const changed = result.elements.filter((e) => e.change_type !== "unchanged");

  const html = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>BIMDelta Report</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1f2937}
  h1{font-size:1.5rem} h2{font-size:1.15rem;margin-top:2rem}
  table{border-collapse:collapse;width:100%;font-size:.875rem}
  th,td{border:1px solid #e5e7eb;padding:.5rem;text-align:left}
  th{background:#f9fafb}
  .added{color:#16a34a} .removed{color:#dc2626} .modified{color:#d97706}
  .badge{display:inline-block;padding:.125rem .5rem;border-radius:.25rem;font-size:.75rem;font-weight:600}
  .badge.added{background:#dcfce7} .badge.removed{background:#fee2e2} .badge.modified{background:#fef3c7}
</style></head><body>
<h1>BIMDelta Change Report</h1>
<p><strong>${result.v1_filename}</strong> → <strong>${result.v2_filename}</strong></p>
<p>Generated ${new Date(result.timestamp).toLocaleString()}</p>

<h2>Summary</h2>
<table><tr><th>v1 elements</th><th>v2 elements</th><th>Added</th><th>Removed</th><th>Modified</th><th>Unchanged</th></tr>
<tr><td>${s.total_v1}</td><td>${s.total_v2}</td>
<td class="added">${s.added}</td><td class="removed">${s.removed}</td>
<td class="modified">${s.modified}</td><td>${s.unchanged}</td></tr></table>

<h2>Changes (${changed.length})</h2>
<table><tr><th>GlobalId</th><th>Class</th><th>Name</th><th>Storey</th><th>Change</th><th>Details</th></tr>
${changed
  .map(
    (el) => `<tr>
  <td><code>${el.global_id}</code></td>
  <td>${el.ifc_class}</td>
  <td>${el.name ?? ""}</td>
  <td>${el.storey ?? ""}</td>
  <td><span class="badge ${el.change_type}">${el.change_type}</span></td>
  <td>${formatDetails(el)}</td>
</tr>`,
  )
  .join("\n")}
</table>
</body></html>`;

  download(html, "bimdelta-report.html", "text/html");
}

function formatDetails(el: ElementDiff): string {
  const parts: string[] = [];
  if (el.geometry_changed) parts.push("Geometry changed");
  if (el.placement_changed) parts.push("Placement changed");
  if (el.type_changed) parts.push(`Type: ${el.old_type_name} → ${el.new_type_name}`);
  if (el.name_changed) parts.push(`Name: ${el.old_name} → ${el.name}`);
  if (el.storey_changed) parts.push(`Storey: ${el.old_storey} → ${el.storey}`);
  for (const p of el.property_changes) {
    parts.push(`${p.pset_name}.${p.property_name}: ${fmtVal(p.old_value)} → ${fmtVal(p.new_value)}`);
  }
  return parts.join("<br>");
}

function fmtVal(v: string | number | boolean | null): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}

function download(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
