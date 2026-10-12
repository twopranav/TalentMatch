// Filter state for the applicants list, and how it turns into query params.
export const EMPTY_FILTERS = {
  q: '',
  statuses: [],
  // Shortlist sub-states; only used by the Shortlisted tab.
  stages: [],
  minScore: '',
  maxScore: '',
  minYears: '',
  maxYears: '',
  resumeSkill: '',
  // { 'Python': 'has' | 'proven' | 'missing' } -- JD skills the recruiter picked
  skills: {},
  skillMode: 'all', // 'all' | 'any'
}

function num(value, min, max) {
  if (value === '' || value == null) return null
  const n = Number(value)
  if (Number.isNaN(n)) return null
  return Math.min(max, Math.max(min, n))
}

// Repeated keys (status=a&status=b) are what FastAPI expects for lists, so
// build URLSearchParams ourselves instead of letting axios add [] brackets.
export function filtersToParams(filters) {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  filters.statuses.forEach((s) => params.append('status', s))
  filters.stages.forEach((s) => params.append('shortlist_stage', s))

  const minScore = num(filters.minScore, 0, 100)
  const maxScore = num(filters.maxScore, 0, 100)
  if (minScore != null) params.set('min_score', minScore)
  if (maxScore != null) params.set('max_score', maxScore)

  const minYears = num(filters.minYears, 0, 80)
  const maxYears = num(filters.maxYears, 0, 80)
  if (minYears != null) params.set('min_years', minYears)
  if (maxYears != null) params.set('max_years', maxYears)

  if (filters.resumeSkill.trim()) params.set('resume_skill', filters.resumeSkill.trim())

  const keyFor = { has: 'skills_matched', proven: 'skills_proven', missing: 'skills_missing' }
  Object.entries(filters.skills).forEach(([skill, mode]) => params.append(keyFor[mode], skill))
  if (Object.keys(filters.skills).length > 1 && filters.skillMode === 'any') {
    params.set('skill_mode', 'any')
  }
  return params
}

export function countActiveFilters(filters) {
  return (
    (filters.q.trim() ? 1 : 0) +
    (filters.statuses.length ? 1 : 0) +
    (filters.stages.length ? 1 : 0) +
    (filters.minScore !== '' || filters.maxScore !== '' ? 1 : 0) +
    (filters.minYears !== '' || filters.maxYears !== '' ? 1 : 0) +
    (filters.resumeSkill.trim() ? 1 : 0) +
    Object.keys(filters.skills).length
  )
}
