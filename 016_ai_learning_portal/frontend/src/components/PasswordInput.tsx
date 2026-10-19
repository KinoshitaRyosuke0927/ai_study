// パスワード入力欄(右端のアイコンで入力内容の表示・非表示を切り替える)
import { useState, type InputHTMLAttributes } from 'react'

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>

const EyeIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const EyeOffIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17.9 17.9A10.6 10.6 0 0 1 12 19c-6.5 0-10-7-10-7a18.5 18.5 0 0 1 4.1-5.1" />
    <path d="M9.9 5.2A9.6 9.6 0 0 1 12 5c6.5 0 10 7 10 7a18.6 18.6 0 0 1-2.2 3.2" />
    <path d="M14.1 14.1a3 3 0 0 1-4.2-4.2" />
    <line x1="2" y1="2" x2="22" y2="22" />
  </svg>
)

export function PasswordInput({ className, ...props }: Props) {
  const [visible, setVisible] = useState(false)
  return (
    <span className="password-field">
      <input {...props} className={className} type={visible ? 'text' : 'password'} />
      <button
        type="button"
        className="password-toggle"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'パスワードを隠す' : 'パスワードを表示'}
        aria-pressed={visible}
        title={visible ? 'パスワードを隠す' : 'パスワードを表示'}
      >
        {visible ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </span>
  )
}
