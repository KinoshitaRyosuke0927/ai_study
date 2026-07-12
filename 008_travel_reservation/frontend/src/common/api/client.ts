// バックエンドAPIのベースURL。
// 環境変数VITE_API_BASE_URLが設定されていればそれを使い、未設定時はローカル開発用のURLにフォールバックする。
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// fetch + res.json()の組み合わせを毎回書かずに済むようにした共通処理。
// 各featureのapiファイルはこのrequestを直接使わず、下のgetJson/postJsonを経由して呼び出す。
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, init)
  return res.json()
}

// GETリクエスト用のヘルパー。パスだけ指定すればよいようにrequestをラップしている。
export function getJson<T>(path: string): Promise<T> {
  return request<T>(path)
}

// POSTリクエスト用のヘルパー。
// Content-Type指定やJSON.stringify化を各apiファイルで重複して書かないよう、ここに集約している。
export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// PUTリクエスト用のヘルパー。
export function putJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// DELETEリクエスト用のヘルパー。
export function deleteJson<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}
