import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { initErrorLog } from './lib/errorLog'
import './index.css'

// S104：前端错误捕获（onerror/unhandledrejection → localStorage，设置页可查看/导出）
initErrorLog()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
