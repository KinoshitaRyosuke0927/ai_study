import { useState } from 'react'
import { login } from '../api/loginApi'
import ErrorMessage from '../../../common/components/ErrorMessage'
import './LoginScreen.css'

type LoginScreenProps = {
  // ログイン成功時に呼び出し元(App)へユーザーID・ユーザー名を渡すコールバック。
  // ログイン後の画面遷移や状態更新はApp側の責務のため、ここでは通知するだけに留めている。
  onLogin: (userId: number, userName: string) => void
}

// ログイン画面。左側にキャッチコピー、右側にログインフォームを表示する2カラムレイアウト。
function LoginScreen({ onLogin }: LoginScreenProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  // パスワードを平文表示するかどうかの切り替え状態。
  const [isPasswordVisible, setIsPasswordVisible] = useState(false)

  // ログインボタン押下時の処理。
  // messagesが空でない場合は認証エラーとみなし、先頭のメッセージを画面に表示する。
  async function handleLogin() {
    setErrorMessage('')
    const response = await login(email, password)
    if (response.messages.length > 0) {
      setErrorMessage(response.messages[0].message)
      return
    }
    // user_id/user_nameが未設定になることは想定していないが、型上optionalなためフォールバックしている。
    onLogin(response.user_id ?? 0, response.user_name ?? '')
  }

  return (
    <div className="login-layout">
      <div className="login-visual">
        <div>
          <div className="brand">AIS Travel</div>
          <div className="visual-copy">
            <h1>
              やさしい旅探しを、
              <br />
              シンプルな体験で。
            </h1>
            <p>
              まだ見ぬ景色に出会う楽しさ、土地ならではの食や文化に触れる喜び、大切な人と過ごす特別な時間。そんな旅の魅力をもっと身近に感じられるように、宿選びから旅のはじまりをやさしくサポートします。
            </p>
          </div>
        </div>
      </div>

      <div className="login-panel-wrap">
        <div className="login-panel">
          <h2>ログイン</h2>
          <div className="field">
            <label className="label" htmlFor="email">
              メールアドレス
            </label>
            <input
              id="email"
              type="email"
              placeholder="example@mail.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="password">
              パスワード
            </label>
            <div className="password-field-wrap">
              <input
                id="password"
                className="password-input"
                type={isPasswordVisible ? 'text' : 'password'}
                placeholder="パスワードを入力"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setIsPasswordVisible((visible) => !visible)}
                aria-label={isPasswordVisible ? 'パスワードを隠す' : 'パスワードを表示'}
              >
                {isPasswordVisible ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a20.3 20.3 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a20.3 20.3 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
          </div>
          <ErrorMessage message={errorMessage} />
          <button className="button" onClick={handleLogin}>
            ログイン
          </button>
        </div>
      </div>
    </div>
  )
}

export default LoginScreen
