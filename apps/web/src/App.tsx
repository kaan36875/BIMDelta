import { useState } from "react";
import { ChangeSummary } from "./components/ChangeSummary";
import { ChangeTable } from "./components/ChangeTable";
import { DetailPanel } from "./components/DetailPanel";
import { ExportMenu } from "./components/ExportMenu";
import { FileUpload } from "./components/FileUpload";
import { QueryBar } from "./components/QueryBar";
import { UrlLoader } from "./components/UrlLoader";
import { Viewer3D } from "./components/Viewer3D";
import { useDiffStore } from "./store/diff-store";
import { clearModelUrls, readModelUrls } from "./utils/model-urls";

export default function App() {
  const { diffResult, error, reset } = useDiffStore();
  const [modelUrls, setModelUrls] = useState(() => readModelUrls(window.location.search));

  const startOver = () => {
    clearModelUrls();
    setModelUrls(null);
    reset();
  };

  if (!diffResult && modelUrls) {
    return <UrlLoader urls={modelUrls} onCancel={startOver} />;
  }

  if (!diffResult) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        {error && (
          <div className="bg-red-50 text-red-700 px-4 py-3 text-sm text-center">
            {error}
          </div>
        )}
        <FileUpload />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-white">
      <header className="flex items-center justify-between px-4 py-2 border-b bg-white shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={startOver}
            className="text-lg font-bold text-gray-900 hover:text-blue-600 transition-colors"
          >
            BIMDelta
          </button>
          <span className="text-xs text-gray-400">
            {diffResult.v1_filename} &rarr; {diffResult.v2_filename}
          </span>
        </div>
        <ExportMenu />
      </header>

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
            <DetailPanel />
          </div>
        </div>
      </div>

      <div className="h-64 border-t shrink-0">
        <ChangeTable />
      </div>
    </div>
  );
}
