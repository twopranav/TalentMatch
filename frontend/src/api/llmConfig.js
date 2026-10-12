import apiClient from './client'

// Admin / superuser only. One row per extraction task: { task, provider, model }.
export function fetchLLMConfigs() {
  return apiClient.get('/admin/llm-config').then((res) => res.data)
}

// Registered provider names, for the provider dropdown.
export function fetchLLMProviders() {
  return apiClient.get('/admin/llm-config/providers').then((res) => res.data)
}

// Takes effect on the very next extraction call. Resolves with the saved row.
export function updateLLMConfig(task, provider, model) {
  return apiClient.put(`/admin/llm-config/${task}`, { provider, model }).then((res) => res.data)
}

// Makes one tiny real call to the provider (spends quota). Always resolves
// with 200 -- failures come back as { ok: false, stage, error }.
export function probeLLMConfig(task) {
  return apiClient.post(`/admin/llm-config/${task}/probe`).then((res) => res.data)
}
