import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// index.htmlの#root要素にReactアプリ全体をマウントするエントリーポイント。
// StrictModeは開発時のみ副作用やレンダリングを2重実行し、不具合を早期発見するためのラッパー。
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
