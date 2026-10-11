import { useCallback, useEffect, useRef, useState } from "react";
import { fetchDiff } from "../api/client";
import { useDiffStore } from "../store/diff-store";

export function FileUpload() {
  const { setDiffResult, setFiles, setLoading, setError, isLoading } =
    useDiffStore();
  const [v1, setV1] = useState<File | null>(null);
  const [v2, setV2] = useState<File | null>(null);
  const v1Ref = useRef<HTMLInputElement>(null);
  const v2Ref = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState("");
  const [eta, setEta] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!v1 || !v2) return;
    setLoading(true);
    setError(null);
    setProgress(0);

    const totalSizeMB = (v1.size + v2.size) / (1024 * 1024);
    const estimatedSeconds = Math.max(8, totalSizeMB * 3);
    const startTime = Date.now();

    intervalRef.current = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000;
      const t = elapsed / estimatedSeconds;
      let p: number;
      if (t < 0.8) {
        p = (t / 0.8) * 85;
      } else {
        p = 85 + 10 * (1 - Math.exp(-(t - 0.8) * 3));
      }
      setProgress(Math.min(p, 95));

      if (p < 25) setStage("Uploading models...");
      else if (p < 55) setStage("Parsing IFC files...");
      else setStage("Comparing elements...");

      const remaining = Math.max(0, estimatedSeconds - elapsed);
      if (remaining <= 0) setEta("Almost done...");
      else if (remaining > 60) setEta(`~${Math.ceil(remaining / 60)} min remaining`);
      else setEta(`~${Math.ceil(remaining)}s remaining`);
    }, 200);

    try {
      setFiles(v1, v2);
      const result = await fetchDiff(v1, v2);
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
      setProgress(100);
      setStage("Done!");
      setEta("");
      setTimeout(() => setDiffResult(result), 400);
    } catch (err) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
      setProgress(0);
      setStage("");
      setEta("");
      setError(err instanceof Error ? err.message : "Diff failed");
      setLoading(false);
    }
  }, [v1, v2, setDiffResult, setFiles, setLoading, setError]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-8 p-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">BIMDelta</h1>
        <p className="text-gray-500">
          Upload two IFC model versions to see what changed
        </p>
      </div>

      <div className="flex gap-6">
        <FileDropZone
          label="Base model (v1)"
          file={v1}
          inputRef={v1Ref}
          onFile={setV1}
        />
        <FileDropZone
          label="Updated model (v2)"
          file={v2}
          inputRef={v2Ref}
          onFile={setV2}
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={!v1 || !v2 || isLoading}
        className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium
                   hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors"
      >
        {isLoading ? stage || "Comparing..." : "Compare Models"}
      </button>

      {isLoading && (
        <div className="w-full max-w-md">
          <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 rounded-full transition-all duration-200 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-sm text-gray-500">
            <span>{Math.round(progress)}%</span>
            <span>{eta}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileDropZone({
  label,
  file,
  inputRef,
  onFile,
}: {
  label: string;
  file: File | null;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onFile: (f: File) => void;
}) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f?.name.toLowerCase().endsWith(".ifc")) onFile(f);
    },
    [onFile],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`w-56 h-40 border-2 border-dashed rounded-xl flex flex-col items-center
                  justify-center cursor-pointer transition-colors
                  ${dragOver ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".ifc"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />
      <span className="text-sm text-gray-500 mb-1">{label}</span>
      {file ? (
        <div className="flex flex-col items-center px-2">
          <span className="text-sm font-medium text-gray-800 truncate max-w-[200px]">
            {file.name}
          </span>
          <span className="text-xs text-gray-400">{formatFileSize(file.size)}</span>
        </div>
      ) : (
        <span className="text-xs text-gray-400">
          Drop .ifc file or click to browse
        </span>
      )}
    </div>
  );
}
