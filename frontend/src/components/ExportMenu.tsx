import { useState } from "react";
import { useDiffStore } from "../store/diff-store";
import { exportCsv, exportHtmlReport } from "../utils/export";

export function ExportMenu() {
  const { diffResult } = useDiffStore();
  const [open, setOpen] = useState(false);

  if (!diffResult) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="px-3 py-1.5 text-sm border rounded-lg hover:bg-gray-50 transition-colors"
      >
        Export &darr;
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-20 bg-white border rounded-lg shadow-lg py-1 w-44">
            <button
              onClick={() => {
                exportCsv(diffResult.elements);
                setOpen(false);
              }}
              className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
            >
              Download CSV
            </button>
            <button
              onClick={() => {
                exportHtmlReport(diffResult);
                setOpen(false);
              }}
              className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50"
            >
              Download HTML Report
            </button>
          </div>
        </>
      )}
    </div>
  );
}
