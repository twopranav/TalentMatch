function escapeIcs(value = '') {
  return String(value).replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/,/g, '\\,').replace(/;/g, '\\;')
}

function toIcsDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z')
}

export function downloadInterviewIcs({ title = 'TalentMatch interview', description = '', start, durationMinutes = 60, location = '' }) {
  const startDate = new Date(start)
  if (!start || Number.isNaN(startDate.getTime())) return false
  const endDate = new Date(startDate.getTime() + durationMinutes * 60_000)
  const now = toIcsDate(new Date())
  const dtStart = toIcsDate(startDate)
  const dtEnd = toIcsDate(endDate)
  const uid = `${Date.now()}-${Math.random().toString(36).slice(2)}@talentmatch`
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//TalentMatch//Interview Calendar//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
    'BEGIN:VEVENT', `UID:${uid}`, `DTSTAMP:${now}`, `DTSTART:${dtStart}`, `DTEND:${dtEnd}`,
    `SUMMARY:${escapeIcs(title)}`, `DESCRIPTION:${escapeIcs(description)}`, `LOCATION:${escapeIcs(location)}`, 'END:VEVENT', 'END:VCALENDAR', '',
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'talentmatch-interview.ics'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
  return true
}
