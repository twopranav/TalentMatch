// Shared by the self-service Profile page and the admin "Edit profile" modal.
// Both talk to endpoints that accept UserProfileUpdate, so the field set is the same.

// Staff accounts show company/title; applicants show the job-seeker fields.
export const isStaffRole = (role) => role === 'recruiter' || role === 'admin' || role === 'superuser'

const STAFF_FIELDS = ['full_name', 'phone', 'company', 'title']
const APPLICANT_FIELDS = ['full_name', 'phone', 'location', 'experience_years', 'desired_role', 'skills']

export function toFormState(user) {
  return {
    full_name: user?.full_name || '',
    phone: user?.phone || '',
    company: user?.company || '',
    title: user?.title || '',
    skills: Array.isArray(user?.skills) ? user.skills.join(', ') : '',
    experience_years: user?.experience_years ?? '',
    location: user?.location || '',
    desired_role: user?.desired_role || '',
  }
}

// Only send the fields the form actually shows for this role, so saving never
// overwrites a field the person could not see.
export function toPayload(form, role) {
  const keys = isStaffRole(role) ? STAFF_FIELDS : APPLICANT_FIELDS
  const payload = {}
  for (const key of keys) payload[key] = form[key]
  if ('skills' in payload) {
    payload.skills = payload.skills ? payload.skills.split(',').map((s) => s.trim()).filter(Boolean) : []
  }
  if ('experience_years' in payload) {
    payload.experience_years = payload.experience_years === '' ? null : Number(payload.experience_years)
  }
  return payload
}
