// Mirrors backend app/core/access.py can_write_job (the server is the real gate).
export function canWriteJob(user, job) {
  if (!user || !job) return false
  if (user.role === 'superuser') return true
  if (user.role === 'admin') return !!user.sub_company && job.sub_company === user.sub_company
  if (user.role === 'recruiter') return job.created_by_id === user.id
  return false
}
