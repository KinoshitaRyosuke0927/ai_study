import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../../components/header/Header.js';
import { showToast } from '../../components/toast/Toast';
import { API_ENDPOINTS, SYSTEM_ERROR_MESSAGE } from '../../utils/constants.js';
import '../../utils/css/util.css';
import './login.css';

export default function Login() {
  const navigate = useNavigate();

  // フォーム入力値
  const [userId, setUserId]       = useState('');
  const [password, setPassword]   = useState('');

  // トースト用メッセージ
  const [message, setMessage]         = useState('');
  const [messageType, setMessageType] = useState('error');

  // メッセージが変化したタイミングでトーストを表示
  useEffect(() => {
    if (!message) return;
    showToast(message, messageType);
  }, [message, messageType]);

  // Enterキーでログインを実行
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.key === 'Enter' && userId.trim() && password.trim()) {
        handleClickLogin(e);
      }
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, password]);

  // ログインボタンクリック・フォーム送信
  const handleClickLogin = async (e) => {
    e?.preventDefault(); // フォーム送信によるページリロードを防止
    setMessage('');

    try {
      const res = await fetch(API_ENDPOINTS.LOGIN, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mail_address: userId, password }),
      });

      // HTTP エラー
      if (!res.ok) {
        setMessageType('error');
        setMessage(SYSTEM_ERROR_MESSAGE);
        return;
      }

      const data = await res.json();

      // ログイン失敗（サーバからエラーメッセージが返却された場合）
      if (Array.isArray(data?.messages) && data.messages.length > 0) {
        setMessageType(data.messages[0]?.message_type ?? 'error');
        setMessage(data.messages[0]?.message ?? SYSTEM_ERROR_MESSAGE);
        return;
      }

      // ログイン情報をセッションストレージに保持（タブを閉じるまで有効）
      if (data?.user_id != null)   sessionStorage.setItem('user_id',   String(data.user_id));
      if (data?.user_name != null) sessionStorage.setItem('user_name', String(data.user_name));

      // タスク一覧画面へ遷移（ログイン直後フラグ付き）
      navigate('/task-list', {
        state: { userName: data?.user_name ?? '', fromLogin: true },
      });
    } catch {
      setMessageType('error');
      setMessage(SYSTEM_ERROR_MESSAGE);
    }
  };

  return (
    <>
      <Header pageTitle="ログイン" showUser={false} />
      <div className="login-page-container">
        <div className="header-spacer"></div>
        <main className="login-main">
          <form className="login-form" onSubmit={handleClickLogin}>

            {/* カード上部：アイコン・タイトル */}
            <div className="login-card-header">
              <div className="login-app-icon">D</div>
              <h1 className="login-card-title">DocAI へようこそ</h1>
              <p className="login-card-subtitle">Pythonコードを自然言語に翻訳するAIツール</p>
            </div>

            {/* メールアドレス入力 */}
            <div className="login-form-group">
              <label className="login-label">メールアドレス</label>
              <input
                type="text"
                placeholder="メールアドレス"
                maxLength={255}
                className="login-input"
                value={userId}
                onChange={e => setUserId(e.target.value)}
              />
            </div>

            {/* パスワード入力 */}
            <div className="login-form-group">
              <label className="login-label">パスワード</label>
              <input
                type="password"
                placeholder="パスワード"
                maxLength={255}
                className="login-input"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </div>

            <button
              type="submit"
              className="login-btn btn bg-info txt-other"
              disabled={!(userId.trim() && password.trim())}
            >
              ログイン
            </button>
          </form>
        </main>
      </div>
    </>
  );
}
