import React, { useCallback, useRef, useState } from "react";
import axios from "axios";

interface GenerateResponse {
  status: string;
  manual_id: string;
  manual_html_url: string;
  manual_json: unknown;
}

interface Props {
  onProcessingStart: () => void;
  onComplete: (data: GenerateResponse) => void;
  onError: (msg: string) => void;
}

const ALLOWED_TYPES = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/avi"];
const MAX_SIZE_MB = 500;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

export default function VideoUploader({ onProcessingStart, onComplete, onError }: Props) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [fileName, setFileName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      onError(`サポートされていないファイル形式です。対応形式: MP4, MOV, AVI, WebM`);
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      onError(`ファイルサイズが${MAX_SIZE_MB}MBを超えています（${(file.size / 1024 / 1024).toFixed(1)}MB）`);
      return;
    }

    setFileName(file.name);
    setIsUploading(true);
    setUploadProgress(0);

    try {
      // Step 1: アップロード
      const formData = new FormData();
      formData.append("video_file", file);

      const uploadRes = await axios.post<{ filename: string; size: number }>(
        "/api/upload",
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (evt) => {
            if (evt.total) {
              setUploadProgress(Math.round((evt.loaded / evt.total) * 100));
            }
          },
        }
      );

      onProcessingStart();

      // Step 2: マニュアル生成
      const generateRes = await axios.post<GenerateResponse>("/api/generate", {
        video_filename: uploadRes.data.filename,
      });

      onComplete(generateRes.data);
    } catch (err: unknown) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : "アップロードまたはマニュアル生成中にエラーが発生しました。";
      onError(message);
      setIsUploading(false);
    }
  }, [onProcessingStart, onComplete, onError]);

  const onDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const onFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  }, [handleFile]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-xl">
        {/* タイトル */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">操作マニュアル自動生成</h1>
          <p className="text-gray-500">画面録画動画をアップロードするとAIがマニュアルを自動作成します</p>
        </div>

        {/* ドロップエリア */}
        {!isUploading ? (
          <div
            className={`border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-colors ${
              isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-white hover:border-blue-400 hover:bg-blue-50"
            }`}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="video/mp4,video/quicktime,video/x-msvideo,video/webm"
              className="hidden"
              onChange={onFileChange}
            />

            <div className="text-5xl mb-4">🎬</div>
            <p className="text-lg font-semibold text-gray-700 mb-1">
              動画をドラッグ&ドロップ
            </p>
            <p className="text-sm text-gray-500 mb-4">またはクリックしてファイルを選択</p>
            <p className="text-xs text-gray-400">対応形式: MP4, MOV, AVI, WebM ／ 最大500MB</p>

            <button
              type="button"
              className="mt-6 inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
              onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            >
              ファイルを選択
            </button>
          </div>
        ) : (
          /* アップロード中 */
          <div className="bg-white rounded-2xl p-8 shadow-sm border border-gray-200">
            <p className="text-sm font-medium text-gray-500 mb-1">アップロード中</p>
            <p className="font-semibold text-gray-800 mb-4 truncate">{fileName}</p>
            <div className="w-full bg-gray-100 rounded-full h-2.5">
              <div
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <p className="text-right text-sm text-gray-500 mt-1">{uploadProgress}%</p>
          </div>
        )}
      </div>
    </div>
  );
}
