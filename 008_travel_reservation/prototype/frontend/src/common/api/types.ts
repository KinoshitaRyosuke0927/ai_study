// バックエンドAPIが返すメッセージの共通フォーマット。
// このアプリのAPIはエラー時もHTTPステータスは200のまま、
// messagesにエラー内容を詰めて返す設計になっているため、
// ログイン・検索・詳細取得などすべてのレスポンス型で共通して使う。
export type ApiMessage = {
  message_id: string
  message_type: string
  message: string
}
