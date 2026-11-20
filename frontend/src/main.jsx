import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { AuthProvider } from './auth/AuthContext.jsx'

const localAuthEnabled =
  import.meta.env.DEV &&
  window.location.hostname === 'localhost' &&
  ['5173', '5174'].includes(window.location.port)


createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider enabled={localAuthEnabled}>
      <App />
    </AuthProvider>
  </StrictMode>,
)
