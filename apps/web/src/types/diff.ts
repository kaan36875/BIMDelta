export type ChangeType = "added" | "removed" | "modified" | "unchanged";
export type MatchMethod = "global_id" | "tag" | "fallback";
export type PropertySource = "occurrence" | "type";

export interface PropertyChange {
  pset_name: string;
  property_name: string;
  source: PropertySource;
  old_value: string | number | boolean | null;
  new_value: string | number | boolean | null;
}

export interface ElementDiff {
  global_id: string;
  ifc_class: string;
  name: string | null;
  storey: string | null;
  change_type: ChangeType;
  match_method: MatchMethod | null;
  matched_global_id: string | null;
  property_changes: PropertyChange[];
  geometry_changed: boolean;
  geometry_unknown?: boolean;
  placement_changed: boolean;
  type_changed: boolean;
  name_changed: boolean;
  storey_changed: boolean;
  ignored_property_changes?: number;
  old_name: string | null;
  old_storey: string | null;
  old_type_name: string | null;
  new_type_name: string | null;
}

export interface StoreyElevationChange {
  storey_name: string;
  old_elevation: number;
  new_elevation: number;
}

export interface OneSidedPset {
  pset_name: string;
  only_in: "v1" | "v2";
  element_count: number;
}

export interface NoiseReport {
  strict: boolean;
  ignore_properties: string[];
  ignored_property_changes: number;
  one_sided_psets: OneSidedPset[];
}

export interface PropertyChangeCount {
  pset_name: string;
  property_name: string;
  element_count: number;
}

export interface DiffSummary {
  total_v1: number;
  total_v2: number;
  added: number;
  removed: number;
  modified: number;
  unchanged: number;
  by_class: Record<string, Record<string, number>>;
  by_storey: Record<string, Record<string, number>>;
  storey_elevation_changes: StoreyElevationChange[];
  geometry_unknown?: number;
  top_changed_properties?: PropertyChangeCount[];
  noise?: NoiseReport | null;
}

export interface DiffResult {
  schema_version: string;
  v1_filename: string;
  v2_filename: string;
  v1_ifc_schema: string;
  v2_ifc_schema: string;
  timestamp: string;
  summary: DiffSummary;
  elements: ElementDiff[];
}
