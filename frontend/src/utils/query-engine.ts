import type { ChangeType, ElementDiff } from "../types/diff";

export interface QueryResult {
  answer: string;
  matchedIds: Set<string>;
}

const CLASS_KEYWORDS: Record<string, string[]> = {
  IfcWall: ["wall", "walls"],
  IfcWallStandardCase: ["wall", "walls"],
  IfcSlab: ["slab", "slabs", "floor", "floors"],
  IfcColumn: ["column", "columns"],
  IfcBeam: ["beam", "beams"],
  IfcDoor: ["door", "doors"],
  IfcWindow: ["window", "windows"],
  IfcStair: ["stair", "stairs", "staircase"],
  IfcRoof: ["roof", "roofs"],
  IfcRailing: ["railing", "railings"],
  IfcCurtainWall: ["curtain wall", "curtain walls"],
  IfcPlate: ["plate", "plates"],
  IfcMember: ["member", "members"],
  IfcFurniture: ["furniture"],
  IfcBuildingElementProxy: ["proxy", "element", "elements"],
  IfcSpace: ["space", "spaces", "room", "rooms"],
  IfcCovering: ["covering", "coverings", "ceiling", "ceilings"],
  IfcFooting: ["footing", "footings", "foundation", "foundations"],
  IfcPile: ["pile", "piles"],
  IfcFlowSegment: ["pipe", "pipes", "duct", "ducts"],
  IfcFlowTerminal: ["terminal", "terminals", "fixture", "fixtures"],
  IfcFlowFitting: ["fitting", "fittings"],
  IfcDistributionPort: ["port", "ports"],
};

const CHANGE_KEYWORDS: Record<ChangeType, string[]> = {
  added: ["added", "new", "created"],
  removed: ["removed", "deleted", "missing", "gone"],
  modified: ["modified", "changed", "updated", "edited", "altered"],
  unchanged: ["unchanged", "same", "unmodified", "untouched"],
};

const DETAIL_KEYWORDS: Record<string, string[]> = {
  geometry: ["geometry", "shape", "mesh", "form"],
  placement: ["placement", "position", "location", "moved", "relocated"],
  property: ["property", "properties", "attribute", "attributes", "parameter"],
  type: ["type", "type name", "product type"],
  name: ["name", "renamed", "naming"],
  storey: ["storey", "story", "floor", "level"],
};

export function executeQuery(
  query: string,
  elements: ElementDiff[],
): QueryResult {
  const q = query.toLowerCase().trim();

  if (!q) return { answer: "", matchedIds: new Set() };

  const classFilter = detectClasses(q, elements);
  const changeFilter = detectChangeTypes(q);
  const storeyFilter = detectStorey(q, elements);
  const detailFilter = detectDetails(q);

  let matches = elements;

  if (classFilter.length > 0) {
    matches = matches.filter((el) =>
      classFilter.some((cls) => el.ifc_class.toLowerCase() === cls.toLowerCase()),
    );
  }

  if (changeFilter.length > 0) {
    matches = matches.filter((el) =>
      changeFilter.includes(el.change_type),
    );
  }

  if (storeyFilter) {
    matches = matches.filter(
      (el) => el.storey?.toLowerCase().includes(storeyFilter),
    );
  }

  if (detailFilter.length > 0) {
    matches = matches.filter((el) =>
      detailFilter.some((d) => {
        if (d === "geometry") return el.geometry_changed;
        if (d === "placement") return el.placement_changed;
        if (d === "property") return el.property_changes.length > 0;
        if (d === "type") return el.type_changed;
        if (d === "name") return el.name_changed;
        if (d === "storey") return el.storey_changed;
        return false;
      }),
    );
  }

  const matchedIds = new Set(matches.map((m) => m.global_id));
  const answer = buildAnswer(matches, classFilter, changeFilter, storeyFilter, detailFilter, elements);

  return { answer, matchedIds };
}

function detectClasses(q: string, elements: ElementDiff[]): string[] {
  const found: string[] = [];

  for (const [cls, keywords] of Object.entries(CLASS_KEYWORDS)) {
    if (keywords.some((kw) => q.includes(kw))) {
      found.push(cls);
    }
  }

  if (found.length === 0) {
    const allClasses = [...new Set(elements.map((e) => e.ifc_class))];
    for (const cls of allClasses) {
      const short = cls.replace(/^Ifc/, "").toLowerCase();
      if (q.includes(short)) {
        found.push(cls);
      }
    }
  }

  return found;
}

function detectChangeTypes(q: string): ChangeType[] {
  const found: ChangeType[] = [];
  for (const [ct, keywords] of Object.entries(CHANGE_KEYWORDS)) {
    if (keywords.some((kw) => q.includes(kw))) {
      found.push(ct as ChangeType);
    }
  }
  return found;
}

function detectStorey(q: string, elements: ElementDiff[]): string | null {
  const storeys = [...new Set(elements.map((e) => e.storey).filter(Boolean))] as string[];

  for (const s of storeys) {
    if (q.includes(s.toLowerCase())) return s.toLowerCase();
  }

  const floorMatch = q.match(/(?:floor|storey|story|level)\s*(\d+)/);
  if (floorMatch) {
    const num = floorMatch[1];
    const matched = storeys.find(
      (s) => s.includes(num) && /floor|storey|story|level|etage/i.test(s),
    );
    if (matched) return matched.toLowerCase();
    const byNumber = storeys.find((s) => s.includes(num));
    if (byNumber) return byNumber.toLowerCase();
  }

  if (q.includes("ground floor") || q.includes("ground level")) {
    const ground = storeys.find((s) => /ground|0|ug|eg/i.test(s));
    if (ground) return ground.toLowerCase();
  }

  if (q.includes("basement")) {
    const base = storeys.find((s) => /basement|under|keller|-1|ug/i.test(s));
    if (base) return base.toLowerCase();
  }

  return null;
}

function detectDetails(q: string): string[] {
  const found: string[] = [];
  for (const [detail, keywords] of Object.entries(DETAIL_KEYWORDS)) {
    if (keywords.some((kw) => q.includes(kw))) {
      found.push(detail);
    }
  }
  return found;
}

function buildAnswer(
  matches: ElementDiff[],
  classFilter: string[],
  changeFilter: ChangeType[],
  storeyFilter: string | null,
  detailFilter: string[],
  allElements: ElementDiff[],
): string {
  if (classFilter.length === 0 && changeFilter.length === 0 && !storeyFilter && detailFilter.length === 0) {
    return summarizeAll(allElements);
  }

  if (matches.length === 0) {
    return "No elements match your query.";
  }

  const parts: string[] = [];

  const classLabel = classFilter.length > 0
    ? classFilter.map((c) => c.replace(/^Ifc/, "")).join("/")
    : "element";

  const changeLabel = changeFilter.length > 0
    ? changeFilter.join("/")
    : null;

  const storeyLabel = storeyFilter ?? null;

  parts.push(`Found ${matches.length} ${classLabel}${matches.length !== 1 ? "s" : ""}`);

  if (changeLabel) parts[0] += ` (${changeLabel})`;
  if (storeyLabel) parts[0] += ` on ${storeyLabel}`;
  parts[0] += ".";

  const byChange: Record<string, number> = {};
  for (const m of matches) {
    byChange[m.change_type] = (byChange[m.change_type] || 0) + 1;
  }

  if (Object.keys(byChange).length > 1 || changeFilter.length === 0) {
    const breakdown = Object.entries(byChange)
      .map(([ct, n]) => `${n} ${ct}`)
      .join(", ");
    parts.push(breakdown);
  }

  if (matches.length <= 8) {
    const names = matches
      .map((m) => m.name || m.global_id)
      .join(", ");
    parts.push(names);
  }

  return parts.join(" — ");
}

function summarizeAll(elements: ElementDiff[]): string {
  const counts: Record<string, number> = {};
  for (const el of elements) {
    counts[el.change_type] = (counts[el.change_type] || 0) + 1;
  }
  const parts = Object.entries(counts)
    .map(([ct, n]) => `${n} ${ct}`)
    .join(", ");
  return `${elements.length} total elements: ${parts}. Try asking about specific types (e.g. "which walls were modified?") or storeys.`;
}
