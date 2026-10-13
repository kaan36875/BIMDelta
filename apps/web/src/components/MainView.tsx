import type { ReactNode } from "react";
import { useDiffStore } from "../store/diff-store";
import { ChangeSummary } from "./ChangeSummary";
import { ChangeTable } from "./ChangeTable";
import { DetailPanel } from "./DetailPanel";
import { ExportMenu } from "./ExportMenu";
import { QueryBar } from "./QueryBar";
import { Viewer3D } from "./Viewer3D";

/** The diff layout: 3D view, summary, element details and the element table. */
export function MainView({
  onHome,
  toolbar,
  history,
}: {
  onHome: () => void;
  toolbar?: ReactNode;
  history?: (globalId: string) => ReactNode;
}) {
  const { diffResult } = useDiffStore();
  if (!diffResult) return null;

  return (
    <div className="h-screen flex flex-col bg-white">
      <header className="flex items-center justify-between px-4 py-2 border-b bg-white shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onHome}
            className="text-lg font-bold text-gray-900 hover:text-blue-600 transition-colors"
          >
            BIMDelta
          </button>
          <span className="text-xs text-gray-400 truncate">
            {diffResult.v1_filename} &rarr; {diffResult.v2_filename}
          </span>
        </div>
        <ExportMenu />
      </header>

      {toolbar && <div className="px-4 py-1 border-b bg-white shrink-0">{toolbar}</div>}

      <div className="px-4 py-2 border-b bg-gray-50 shrink-0">
        <QueryBar />
      </div>

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 min-w-0">
          <Viewer3D />
        </div>

        <div className="w-80 border-l flex flex-col bg-white shrink-0">
          <div className="p-4 border-b">
            <ChangeSummary />
          </div>
          <div className="flex-1 overflow-auto border-b">
            <DetailPanel history={history} />
          </div>
        </div>
      </div>

      <div className="h-64 border-t shrink-0">
        <ChangeTable />
      </div>
    </div>
  );
}
