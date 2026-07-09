import { useState } from 'react'
import { login } from '../api/loginApi'
import ErrorMessage from '../../../common/components/ErrorMessage'
import './LoginScreen.css'

type LoginScreenProps = {
  // ログイン成功時に呼び出し元(App)へユーザー名を渡すコールバック。
  // ログイン後の画面遷移や状態更新はApp側の責務のため、ここでは通知するだけに留めている。
  onLogin: (userName: string) => void
}

// ログイン画面。左側にキャッチコピー、右側にログインフォームを表示する2カラムレイアウト。
function LoginScreen({ onLogin }: LoginScreenProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  // ログインボタン押下時の処理。
  // messagesが空でない場合は認証エラーとみなし、先頭のメッセージを画面に表示する。
  async function handleLogin() {
    setErrorMessage('')
    const response = await login(email, password)
    if (response.messages.length > 0) {
      setErrorMessage(response.messages[0].message)
      return
    }
    // user_nameが未設定になることは想定していないが、型上optionalなため空文字にフォールバックしている。
    onLogin(response.user_name ?? '')
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
            <input
              id="password"
              type="password"
              placeholder="パスワードを入力"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
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
