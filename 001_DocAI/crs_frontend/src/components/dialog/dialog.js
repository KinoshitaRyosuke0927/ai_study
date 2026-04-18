import '../../lib/destyle.css-master/destyle.min.css';
import '../../utils/css/util.css';
import './dialog.css';

/**
 * 確認ダイアログコンポーネント
 * @param {boolean} isOpen - ダイアログの表示/非表示
 * @param {string} title - ダイアログのタイトル
 * @param {string} message - ダイアログに表示するメッセージ
 * @param {string} titleToConfirm - 実行側のボタンのタイトル
 * @param {string} colorToConfirm - 実行側のボタンの色（デフォルトは'bg-info'）
 * @param {function} onConfirm - 実行側のボタンを選択したときのコールバック
 * @param {string} titleToCancel - キャンセル側のボタンのタイトル
 * @param {string} colorToCancel - キャンセル側のボタンの色（デフォルトは'bg-info'）
 * @param {function} onCancel - キャンセル側のボタンを選択したときのコールバック
 */
export default function Dialog({ isOpen, title, message, titleToConfirm, colorToConfirm = 'bg-info', onConfirm, titleToCancel, colorToCancel = 'bg-info', onCancel }) {
    if (!isOpen) return null;

    const lines = message.split('\n');

    return (
        <div className="dialog-overlay" onClick={onCancel}>
            <div className="dialog-container" onClick={e => e.stopPropagation()}>
                <div className="dialog-header">
                    <h2 className="dialog-title">{title}</h2>
                </div>
                <div className="dialog-body">
                    <p className="dialog-message">
                        {lines.map((line, index) => (
                            <span key={index}>
                                {line}
                                {index < lines.length - 1 && <br />}
                            </span>
                        ))}
                    </p>
                    <div className="dialog-buttons">
                        <button
                            className={`btn ${colorToConfirm}`}
                            onClick={onConfirm}
                        >
                            {titleToConfirm}
                        </button>
                        <button
                            className={`btn ${colorToCancel}`}
                            onClick={onCancel}
                        >
                            {titleToCancel}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
