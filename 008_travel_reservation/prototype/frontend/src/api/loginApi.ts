import { API_BASE_URL } from './client'

export type LoginMessage = {
  message_id: string
  message_type: string
  message: string
}

export type LoginResponse = {
  messages: LoginMessage[]
  user_id?: number | null
  user_name?: string
}

export async function login(mailAddress: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mail_address: mailAddress, password }),
  })
  return res.json()
}
