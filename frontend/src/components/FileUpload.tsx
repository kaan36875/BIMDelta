import { useCallback, useRef, useState } from "react";
import { fetchDiff } from "../api/client";
import { useDiffStore } from "../store/diff-store";

export function FileUpload() {
  const { setDiffResult, setFiles, setLoading, setError, isLoading } =
    useDiffStore();
  const [v1, setV1] = useState<File | null>(null);
  const [v2, setV2] = useState<File | null>(null);
  const v1Ref = useRef<HTMLInputElement>(null);
  const v2Ref = useRef<HTMLInputElement>(null);

  const handleSubmit = useCallback(async () => {
    if (!v1 || !v2) return;
    setLoading(true);
    setError(null);
    try {
      setFiles(v1, v2);
      const result = await fetchDiff(v1, v2);
      setDiffResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Diff failed");
    } finally {
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
        {isLoading ? "Comparing..." : "Compare Models"}
      </button>
    </div>
  );
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
        <span className="text-sm font-medium text-gray-800 truncate max-w-[200px] px-2">
          {file.name}
        </span>
      ) : (
        <span className="text-xs text-gray-400">
          Drop .ifc file or click to browse
        </span>
      )}
    </div>
  );
}
