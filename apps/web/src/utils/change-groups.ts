import type { ElementDiff, PropertyChange } from "../types/diff";

export type ChangeGroup = "geometry" | "type" | "material" | "properties";

export const GROUP_LABELS: Record<ChangeGroup, string> = {
  geometry: "Geometry",
  type: "Type",
  material: "Material",
  properties: "Properties",
};

/** One old → new line in a detail tab. */
export interface ChangeRow {
  label: string;
  detail?: string; // e.g. the property set
  old: string;
  new: string;
}

const isQuantity = (p: PropertyChange) =>
  p.pset_name.startsWith("Qto_") || /quantit/i.test(p.pset_name);
const isMaterial = (p: PropertyChange) =>
  /material/i.test(p.pset_name) || /material/i.test(p.property_name);

/** Which tab a property change belongs in: quantities describe the shape, material
 * sets the material, type properties the type; everything else is a plain property. */
export function propertyGroup(p: PropertyChange): ChangeGroup {
  if (isQuantity(p)) return "geometry";
  if (isMaterial(p)) return "material";
  if (p.source === "type") return "type";
  return "properties";
}

export function formatValue(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(+v.toFixed(4));
  return String(v);
}

const mm = (m: number) => `${Math.round(m * 1000)}`;

export function groupChanges(el: ElementDiff): Record<ChangeGroup, ChangeRow[]> {
  const groups: Record<ChangeGroup, ChangeRow[]> = {
    geometry: [],
    type: [],
    material: [],
    properties: [],
  };

  if (el.placement_changed) {
    groups.geometry.push({ label: "Placement", old: "", new: "moved" });
  }
  if (el.geometry_changed) {
    const o = el.old_geometry;
    const n = el.new_geometry;
    if (o && n) {
      groups.geometry.push({
        label: "Bounding box",
        detail: "mm",
        old: o.bbox_dims.map(mm).join(" × "),
        new: n.bbox_dims.map(mm).join(" × "),
      });
      groups.geometry.push({
        label: "Volume",
        detail: "m³",
        old: o.volume.toFixed(3),
        new: n.volume.toFixed(3),
      });
      if (o.offset && n.offset) {
        const shift = n.offset.map((v, i) => Math.round((v - o.offset![i]) * 1000));
        if (shift.some((d) => d !== 0)) {
          groups.geometry.push({
            label: "Shape moved",
            detail: "x, y, z mm, in the element's own axes",
            old: "",
            new: shift.map((d) => (d > 0 ? `+${d}` : `${d}`)).join(", "),
          });
        }
      }
    } else {
      groups.geometry.push({ label: "Shape", old: "", new: "changed" });
    }
  }
  if (el.type_changed) {
    groups.type.push({
      label: "Type",
      old: el.old_type_name ?? "—",
      new: el.new_type_name ?? "—",
    });
  }
  if (el.material_changed) {
    groups.material.push({
      label: "Material",
      old: el.old_material ?? "—",
      new: el.new_material ?? "—",
    });
  }
  if (el.name_changed) {
    groups.properties.push({ label: "Name", old: el.old_name ?? "—", new: el.name ?? "—" });
  }
  if (el.storey_changed) {
    groups.properties.push({
      label: "Storey",
      old: el.old_storey ?? "—",
      new: el.storey ?? "—",
    });
  }
  for (const p of el.property_changes) {
    groups[propertyGroup(p)].push({
      label: p.property_name,
      detail: p.source === "type" ? `${p.pset_name} (type)` : p.pset_name,
      old: formatValue(p.old_value),
      new: formatValue(p.new_value),
    });
  }
  return groups;
}
