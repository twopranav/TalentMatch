// Status choices a recruiter can set on an application. The backend enum also
// has "hired", which is deliberately not offered here; rows already in that
// state still display (see statusOptionsFor).
export const APPLICATION_STATUS_OPTIONS = ['applied', 'under_review', 'shortlisted', 'rejected']

export const APPLICATION_STATUS_LABELS = {
  applied: 'Applied',
  under_review: 'Reviewing',
  shortlisted: 'Shortlisted',
  rejected: 'Rejected',
  hired: 'Hired',
}

export function statusLabel(value) {
  return APPLICATION_STATUS_LABELS[value] ?? value
}

// Options for one row's <select>: the standard four, plus the row's current
// value if it is something else (e.g. a legacy "hired"), so the select never
// shows a wrong value.
export function statusOptionsFor(current) {
  return APPLICATION_STATUS_OPTIONS.includes(current) || !current
    ? APPLICATION_STATUS_OPTIONS
    : [...APPLICATION_STATUS_OPTIONS, current]
}

// Shortlist sub-states. "shortlisted" is the default on entering the shortlist.
export const SHORTLIST_STAGE_OPTIONS = ['shortlisted', 'review', 'interview_scheduled', 'rejected']

export const SHORTLIST_STAGE_LABELS = {
  shortlisted: 'Shortlisted',
  review: 'Review',
  interview_scheduled: 'Interview scheduled',
  rejected: 'Rejected',
}

export function stageLabel(value) {
  return SHORTLIST_STAGE_LABELS[value] ?? value
}

// <input type="datetime-local"> works in local time without a zone; the API
// wants an unambiguous instant. These convert between the two.
function pad(n) {
  return String(n).padStart(2, '0')
}

export function isoToLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function localInputToIso(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

export function formatInterviewTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}
