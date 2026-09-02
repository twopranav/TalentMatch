import { useEffect, useState } from 'react'
import apiClient from './api/client'

function App() {
  const [status, setStatus] = useState('checking...')

  useEffect(() => {
    apiClient
      .get('/health')
      .then((res) => setStatus(res.data.status))
      .catch(() => setStatus('backend unreachable'))
  }, [])

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>Resume Filter Application</h1>
      <p>Backend status: {status}</p>
      {/* Phase 2 replaces this with routed pages: login, job dashboard, etc. */}
    </div>
  )
}

export default App