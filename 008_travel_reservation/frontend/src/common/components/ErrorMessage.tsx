import './ErrorMessage.css'

type ErrorMessageProps = {
  message: string
}

// ログイン画面・検索画面・詳細画面で共通して使うエラー表示部品。
// メッセージが空文字のときは何も表示したくないため、ここでnullを返して呼び出し側の条件分岐を省略できるようにしている。
function ErrorMessage({ message }: ErrorMessageProps) {
  if (!message) return null
  return <div className="error-message">{message}</div>
}

export default ErrorMessage
