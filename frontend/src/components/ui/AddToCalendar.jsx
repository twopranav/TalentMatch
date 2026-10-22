import ActionMenu from './ActionMenu'
import { downloadInterviewIcs, googleCalendarUrl, outlookCalendarUrl } from '../../utils/calendar'

// "Add to calendar" opens Google Calendar or Outlook on the web in a new tab
// with the event pre-filled. A .ics download is offered as the last option for
// desktop calendar apps; that one is the only choice that saves a file.
export default function AddToCalendar({ event, label = 'Add to calendar', align = 'end' }) {
  if (!event?.start || Number.isNaN(new Date(event.start).getTime())) return null
  const open = (url) => window.open(url, '_blank', 'noopener,noreferrer')
  return <ActionMenu
    label={label}
    align={align}
    trigger={<><span className="text-xs font-semibold">{label}</span><span aria-hidden="true" className="ml-1 text-slate-400">⌄</span></>}
    items={[
      { label: 'Google Calendar', onSelect: () => open(googleCalendarUrl(event)) },
      { label: 'Outlook on the web', onSelect: () => open(outlookCalendarUrl(event)) },
      { label: 'Download .ics file', onSelect: () => downloadInterviewIcs(event) },
    ]}
  />
}
