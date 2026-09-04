const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed with status ${response.status}`)
  }
  return response.json()
}

export const api = {
  users: () => request('/api/users/demo'),
  documents: () => request('/api/documents'),
  logs: () => request('/api/chat/logs'),
  evaluations: () => request('/api/evaluations'),
  runEvaluation: () => request('/api/evaluations/run', { method: 'POST' }),
  chat: (payload) =>
    request('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  uploadDocument: (payload) => {
    const form = new FormData()
    form.append('file', payload.file)
    form.append('title', payload.title)
    form.append('department', payload.department)
    form.append('roles', payload.roles)
    return request('/api/documents/upload', { method: 'POST', body: form })
  },
  updateDocument: (documentId, payload) =>
    request(`/api/documents/${documentId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
}
