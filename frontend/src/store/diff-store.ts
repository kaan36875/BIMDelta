import { create } from "zustand";
import type { ChangeType, DiffResult, ElementDiff } from "../types/diff";

interface DiffState {
  diffResult: DiffResult | null;
  v1File: File | null;
  v2File: File | null;
  selectedElementId: string | null;
  filterChangeType: ChangeType | null;
  filterClass: string | null;
  filterStorey: string | null;
  searchText: string;
  isLoading: boolean;
  error: string | null;

  setDiffResult: (result: DiffResult) => void;
  setFiles: (v1: File, v2: File) => void;
  selectElement: (id: string | null) => void;
  setFilterChangeType: (type: ChangeType | null) => void;
  setFilterClass: (cls: string | null) => void;
  setFilterStorey: (storey: string | null) => void;
  setSearchText: (text: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useDiffStore = create<DiffState>((set) => ({
  diffResult: null,
  v1File: null,
  v2File: null,
  selectedElementId: null,
  filterChangeType: null,
  filterClass: null,
  filterStorey: null,
  searchText: "",
  isLoading: false,
  error: null,

  setDiffResult: (result) => set({ diffResult: result, error: null }),
  setFiles: (v1, v2) => set({ v1File: v1, v2File: v2 }),
  selectElement: (id) => set({ selectedElementId: id }),
  setFilterChangeType: (type) => set({ filterChangeType: type }),
  setFilterClass: (cls) => set({ filterClass: cls }),
  setFilterStorey: (storey) => set({ filterStorey: storey }),
  setSearchText: (text) => set({ searchText: text }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  reset: () =>
    set({
      diffResult: null,
      v1File: null,
      v2File: null,
      selectedElementId: null,
      filterChangeType: null,
      filterClass: null,
      filterStorey: null,
      searchText: "",
      isLoading: false,
      error: null,
    }),
}));

export function useFilteredElements(): ElementDiff[] {
  const { diffResult, filterChangeType, filterClass, filterStorey, searchText } =
    useDiffStore();

  if (!diffResult) return [];

  return diffResult.elements.filter((el) => {
    if (filterChangeType && el.change_type !== filterChangeType) return false;
    if (filterClass && el.ifc_class !== filterClass) return false;
    if (filterStorey && el.storey !== filterStorey) return false;
    if (searchText) {
      const q = searchText.toLowerCase();
      const haystack = [el.global_id, el.ifc_class, el.name, el.storey]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}
