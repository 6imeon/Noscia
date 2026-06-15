import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles/theme.css'
import App from './App.tsx'
import { Landing } from './views/Landing.tsx'

// No router in the app shell — route the marketing page by path. The console stays at '/',
// the editorial landing renders at '/landing'.
const isLanding = window.location.pathname.replace(/\/+$/, '') === '/landing'

createRoot(document.getElementById('root')!).render(
  <StrictMode>{isLanding ? <Landing /> : <App />}</StrictMode>,
)
