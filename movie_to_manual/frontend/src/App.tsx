import { useState } from "react";
import VideoUploader from "./components/VideoUploader";
import ProgressTracker from "./components/ProgressTracker";
import ManualViewer from "./components/ManualViewer";

type AppState = "idle" | "processing" | "completed";

interface GenerateResponse {
  status: string;
  manual_id: string;
  manual_html_url: string;
  manual_json: unknown;
}

export default function App() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [manualData, setManualData] = useState<GenerateResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");

  const handleProcessingStart = () => {
    setErrorMsg("");
    setAppState("processing");
  };

  const handleComplete = (data: GenerateResponse) => {
    setManualData(data);
    setAppState("completed");
  };

  const handleError = (msg: string) => {
    setErrorMsg(msg);
    setAppState("idle");
  };

  const handleReset = () => {
    setManualData(null);
    setErrorMsg("");
    setAppState("idle");
  };

  return (
    <>
      {appState === "idle" && (
        <div>
          <VideoUploader
            onProcessingStart={handleProcessingStart}
            onComplete={handleComplete}
            onError={handleError}
          />
          {errorMsg && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-red-600 text-white px-6 py-3 rounded-xl shadow-lg max-w-md text-sm text-center">
              {errorMsg}
            </div>
          )}
        </div>
      )}

      {appState === "processing" && (
        <ProgressTracker currentStep={0} />
      )}

      {appState === "completed" && manualData && (
        <ManualViewer
          manualData={manualData as Parameters<typeof ManualViewer>[0]["manualData"]}
          onReset={handleReset}
        />
      )}
    </>
  );
}
