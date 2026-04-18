import './loading.css';

/**
 * ローディングオーバーレイコンポーネント
 * @param {boolean}      show     - 表示フラグ（falseの場合は非表示）
 * @param {string}       message  - 表示するメッセージ
 * @param {number|null}  progress - プログレスバーの値（0〜100）。nullの場合はスピナー表示
 */
export default function Loading({
  show = false,
  message = '処理中...',
  progress = null,
}) {
  if (!show) return null;

  return (
    <div className="loading-overlay">
      <div className="loading-container">
        {progress === null ? (
          // プログレスバーなし：ドットスピナーを表示
          <div className="loading-spinner">
            {[...Array(8)].map((_, i) => (
              <div key={i} className={`loading-dot loading-dot-${i + 1}`}></div>
            ))}
          </div>
        ) : (
          // プログレスバーあり：進捗率を表示（0〜100%にクランプ）
          <div className="loading-progress-container">
            <div
              className="loading-progress-bar"
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
            ></div>
          </div>
        )}
        {message && (
          <div className="loading-message txt-other fs-lg">{message}</div>
        )}
      </div>
    </div>
  );
}
