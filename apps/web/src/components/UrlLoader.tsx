import { useEffect, useState } from "react";
import { downloadModel, fetchDiffFromUrls, modelLabel } from "../api/client";
import { useDiffStore } from "../store/diff-store";
import type { ModelUrls } from "../utils/model-urls";

/**
 * Opens two remote models: the server computes the diff while the browser downloads both
 * files for the 3D view.
 */
export function UrlLoader({ urls, onCancel }: { urls: ModelUrls; onCancel: () => void }) {
  const { setDiffResult, setFiles } = useDiffStore();
  const [stage, setStage] = useState("Downloading models and comparing…");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const labels = [modelLabel(urls.v1Url), modelLabel(urls.v2Url)];

    (async () => {
      try {
        const files = Promise.all([downloadModel(urls.v1Url), downloadModel(urls.v2Url)]).then(
          (downloaded) => {
            if (!cancelled) setStage("Comparing elements…");
            return downloaded;
          },
        );
        const [[v1, v2], result] = await Promise.all([
          files,
          fetchDiffFromUrls(urls.v1Url, urls.v2Url),
        ]);
        if (cancelled) return;
        setFiles(v1, v2);
        setDiffResult({ ...result, v1_filename: labels[0], v2_filename: labels[1] });
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not open the models");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [urls, setDiffResult, setFiles]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-3xl font-bold text-gray-900">BIMDelta</h1>
      <div className="text-sm text-gray-600 text-center space-y-1 break-all max-w-xl">
        <div>{modelLabel(urls.v1Url)}</div>
        <div className="text-gray-400">&darr;</div>
        <div>{modelLabel(urls.v2Url)}</div>
      </div>

      {error ? (
        <div className="max-w-xl w-full bg-red-50 text-red-700 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      ) : (
        <div className="flex items-center gap-3 text-gray-500">
          <span className="h-4 w-4 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
          <span>{stage}</span>
        </div>
      )}

      <button onClick={onCancel} className="text-sm text-blue-600 hover:underline">
        Compare files from your computer instead
      </button>
    </div>
  );
}
