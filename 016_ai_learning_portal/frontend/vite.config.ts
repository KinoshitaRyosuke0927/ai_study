import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 開発時は /api をバックエンド(uvicorn, ポート 8000)へ転送する。
// 本番はビルド成果物(dist)をバックエンドが同じオリジンで配信する。
export default defineConfig({
  plugins: [react()],
  // Pyodide 314 系はモジュール Worker が必要
  worker: {
    format: 'es',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
