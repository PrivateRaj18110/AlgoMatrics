import { useEffect } from 'react'

/**
 * The Ops UI is no longer a public product. Telemetry ingest stays on
 * /ops/api/* (nginx). Visitors are sent into the main application, which
 * then requires the existing JWT session.
 */
export default function App() {
  useEffect(() => {
    window.location.replace('/app/dashboard')
  }, [])
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      Checking session...
    </div>
  )
}
