import type { ChangeType } from "../types/diff";

export const CHANGE_COLORS: Record<ChangeType, string> = {
  added: "#22c55e",
  removed: "#ef4444",
  modified: "#f59e0b",
  unchanged: "#d1d5db",
};

export const CHANGE_COLORS_HEX: Record<ChangeType, number> = {
  added: 0x22c55e,
  removed: 0xef4444,
  modified: 0xf59e0b,
  unchanged: 0xd1d5db,
};

export const CHANGE_LABELS: Record<ChangeType, string> = {
  added: "Added",
  removed: "Removed",
  modified: "Modified",
  unchanged: "Unchanged",
};
