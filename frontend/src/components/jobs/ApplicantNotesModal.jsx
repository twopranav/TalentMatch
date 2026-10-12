import { useCallback, useEffect, useRef, useState } from 'react'
import Modal from '../ui/Modal'
import Spinner from '../ui/Spinner'
import { useToast } from '../ui/Toast'
import { addApplicationNote, fetchApplicationNotes } from '../../api/applications'
import { getErrorMessage } from '../../utils/format'

const MAX_NOTE_LENGTH = 2000 // keep in sync with MAX_NOTE_LENGTH in backend/app/schemas/application_note.py

function formatNoteTime(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

// Popup with a recruiter's notes on one applicant: add a note, read the
// history (newest first). Opened from the shortlist tab.
//
// `applicant` is the applicant row, or null while closed. The component stays
// mounted either way, so a half-written note survives an accidental close
// (Escape, a click outside) and is still there when the same applicant is
// reopened.
export default function ApplicantNotesModal({ applicant, onClose }) {
  const { showToast } = useToast()
  const applicationId = applicant?.id ?? null
  const name = applicant?.applicant_name || applicant?.applicant_email || 'applicant'

  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [drafts, setDrafts] = useState({}) // applicationId -> unsaved text
  const [saving, setSaving] = useState(false)
  const requestId = useRef(0)

  const draft = drafts[applicationId] ?? ''
  const setDraft = (text) => setDrafts((prev) => ({ ...prev, [applicationId]: text }))

  // Only the newest request may update state, so reopening on a different
  // applicant can't show the previous applicant's notes.
  const loadNotes = useCallback(async () => {
    if (!applicationId) return
    requestId.current += 1
    const id = requestId.current
    setLoading(true)
    setError(null)
    setNotes([])
    try {
      const result = await fetchApplicationNotes(applicationId)
      if (id === requestId.current) setNotes(result)
    } catch (err) {
      if (id === requestId.current) setError(getErrorMessage(err, 'Could not load notes.'))
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [applicationId])

  useEffect(() => {
    loadNotes()
  }, [loadNotes])

  const canSubmit = draft.trim().length > 0 && !saving

  const handleAdd = async () => {
    if (!canSubmit) return
    setSaving(true)
    try {
      const saved = await addApplicationNote(applicationId, draft.trim())
      setNotes((prev) => [saved, ...prev])
      setDraft('')
      showToast('Note added.', 'success')
    } catch (err) {
      // The draft is kept, so nothing the recruiter typed is lost.
      showToast(getErrorMessage(err, 'Could not add the note.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleAdd()
    }
  }

  return (
    <Modal
      open={applicant != null}
      onClose={onClose}
      title={`Notes for ${name}`}
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Done
        </button>
      }
    >
      <div className="space-y-4">
        <div>
          <label htmlFor="new-note" className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">
            Add a note
          </label>
          <textarea
            id="new-note"
            rows={3}
            maxLength={MAX_NOTE_LENGTH}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={saving}
            placeholder="Interview impressions, follow-ups, concerns…"
            className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
          <div className="mt-1 flex items-center justify-between gap-3">
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Only recruiters and admins can see notes. Candidates never can.
            </p>
            <span className="shrink-0 text-xs tabular-nums text-slate-400 dark:text-slate-500">
              {draft.length}/{MAX_NOTE_LENGTH}
            </span>
          </div>
          <div className="mt-2 flex justify-end">
            <button
              type="button"
              onClick={handleAdd}
              disabled={!canSubmit}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:ring-offset-slate-900"
            >
              {saving ? 'Adding…' : 'Add note'}
            </button>
          </div>
        </div>

        <div className="border-t border-slate-200 pt-4 dark:border-slate-700">
          {loading ? (
            <div className="flex justify-center py-4"><Spinner size="sm" label="Loading notes" /></div>
          ) : error ? (
            <div className="text-sm text-red-600 dark:text-red-400">
              {error}{' '}
              <button type="button" onClick={loadNotes} className="font-medium underline hover:no-underline">
                Try again
              </button>
            </div>
          ) : notes.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No notes yet. Add the first one above.</p>
          ) : (
            <ul className="space-y-3" aria-label="Notes, newest first">
              {notes.map((note) => (
                <li key={note.id} className="rounded-lg bg-slate-50 px-3 py-2.5 dark:bg-slate-800/60">
                  {/* pre-wrap keeps the recruiter's line breaks; break-words stops a long
                      unbroken string (a URL) from stretching the popup sideways. */}
                  <p className="whitespace-pre-wrap break-words text-sm text-slate-800 dark:text-slate-100">{note.body}</p>
                  <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">
                    {note.author_email || 'Former team member'} on {formatNoteTime(note.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  )
}
