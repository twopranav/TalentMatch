import apiClient from './client'

// One page of audit history, newest first. Returns { items, total }: total is
// the size of the whole filtered set (the X-Total-Count header), not just this
// page. filters: { resource_type, action, job_id, resource_id, actor_id } --
// only truthy keys are sent. The backend scopes results by role on its own
// (recruiters only ever get entries about their own jobs).
export function fetchAuditPage(filters, limit, offset) {
  const params = { limit, offset }
  for (const key of ['resource_type', 'action', 'job_id', 'resource_id', 'actor_id']) {
    if (filters[key]) params[key] = filters[key]
  }
  return apiClient.get('/audit', { params }).then((res) => ({
    items: res.data,
    total: Number(res.headers['x-total-count'] ?? res.data.length),
  }))
}
