import { useState } from "react";
import { isLocalMode } from "./api/local";
import { FileUpload } from "./components/FileUpload";
import { MainView } from "./components/MainView";
import { RepoView } from "./components/RepoView";
import { UrlLoader } from "./components/UrlLoader";
import { useDiffStore } from "./store/diff-store";
import { clearModelUrls, readModelUrls } from "./utils/model-urls";

export default function App() {
  const { diffResult, error, reset } = useDiffStore();
  const [modelUrls, setModelUrls] = useState(() => readModelUrls(window.location.search));

  if (isLocalMode()) return <RepoView />;

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
          <div className="bg-red-50 text-red-700 px-4 py-3 text-sm text-center">{error}</div>
        )}
        <FileUpload />
      </div>
    );
  }

  return <MainView onHome={startOver} />;
}
