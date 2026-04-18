import { useEffect, useState } from "react";

interface Step {
  label: string;
  note?: string;
  delayMs: number;
}

const STEPS: Step[] = [
  { label: "動画のアップロード完了", delayMs: 0 },
  { label: "キーフレームの抽出中...", delayMs: 3000 },
  { label: "AIによる動画解析中...", note: "※AIの解析には数十秒かかる場合があります", delayMs: 13000 },
  { label: "マニュアルの生成中...", delayMs: 25000 },
];

interface Props {
  currentStep: number; // 外部から完了を通知する場合に使用（今は内部タイマーで進行）
}

export default function ProgressTracker(_props: Props) {
  const [completedUntil, setCompletedUntil] = useState(-1);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    // Step 0 は即時完了
    setCompletedUntil(0);
    setActiveStep(1);

    const timers: ReturnType<typeof setTimeout>[] = [];

    for (let i = 1; i < STEPS.length; i++) {
      const step = STEPS[i];
      // 前のステップを「完了」に変える
      timers.push(
        setTimeout(() => {
          setCompletedUntil(i);
          setActiveStep(i + 1);
        }, step.delayMs)
      );
    }

    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">マニュアルを生成中...</h2>
          <p className="text-gray-500 text-sm">しばらくお待ちください</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          <ul className="space-y-6">
            {STEPS.map((step, index) => {
              const isDone = index <= completedUntil;
              const isActive = index === activeStep - 1 && !isDone;
              const isPending = index > completedUntil && !isActive;

              return (
                <li key={index} className="flex items-start gap-4">
                  {/* アイコン */}
                  <div className="flex-shrink-0 mt-0.5">
                    {isDone ? (
                      <div className="w-7 h-7 rounded-full bg-green-100 flex items-center justify-center">
                        <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                    ) : isActive ? (
                      <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center">
                        <svg
                          className="w-4 h-4 text-blue-600 animate-spin"
                          fill="none"
                          viewBox="0 0 24 24"
                        >
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                      </div>
                    ) : (
                      <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center">
                        <div className="w-2 h-2 rounded-full bg-gray-300" />
                      </div>
                    )}
                  </div>

                  {/* テキスト */}
                  <div>
                    <p
                      className={`font-medium ${
                        isDone ? "text-gray-800" : isActive ? "text-blue-700" : "text-gray-400"
                      }`}
                    >
                      {step.label}
                    </p>
                    {step.note && (isActive || isDone) && (
                      <p className="text-xs text-gray-400 mt-0.5">{step.note}</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
