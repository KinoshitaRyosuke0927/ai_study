import { postJson } from '../../../common/api/client'
import type { ApiMessage } from '../../../common/api/types'

// ログインAPIのレスポンス型。
// 認証に失敗した場合はuser_id/user_nameが返らず、messagesにエラー内容が入る想定。
export type LoginResponse = {
  messages: ApiMessage[]
  user_id?: number | null
  user_name?: string
}

// メールアドレスとパスワードでログインするAPIを呼び出す。
// バックエンドのフィールド名(mail_address)に合わせてリクエストボディを組み立てている。
export function login(mailAddress: string, password: string): Promise<LoginResponse> {
  return postJson('/login', { mail_address: mailAddress, password })
}
