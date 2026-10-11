import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import "devices.css/dist/devices.min.css";
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorPage.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary><App /></ErrorBoundary>
  </StrictMode>,
)
