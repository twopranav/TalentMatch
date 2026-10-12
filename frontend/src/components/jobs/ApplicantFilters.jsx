import { useEffect, useRef, useState } from 'react'
import { countActiveFilters, EMPTY_FILTERS } from '../../utils/applicantFilters'
import { APPLICATION_STATUS_OPTIONS, SHORTLIST_STAGE_OPTIONS, stageLabel, statusLabel } from '../../utils/applicantStatus'

// Clicking a JD skill chip cycles: off -> has -> proven -> missing -> off.
const SKILL_CYCLE = [null, 'has', 'proven', 'missing']
const SKILL_STYLE = {
  has: 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  proven: 'border-indigo-300 bg-indigo-50 text-indigo-800 dark:border-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300',
  missing: 'border-red-300 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-900/30 dark:text-red-300',
}
const SKILL_LABEL = { has: 'has', proven: 'proven', missing: 'missing' }

const input = 'rounded border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'
const label = 'mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400'

// value/onChange hold the APPLIED filters. Typing is debounced so the list
// doesn't refetch on every keystroke; clicks apply immediately.
// mode='shortlisted' swaps the Status chips for shortlist-stage chips (the
// Shortlisted tab already pins status to shortlisted).
export default function ApplicantFilters({ value, onChange, jdSkills = [], mode = 'all' }) {
  const [draft, setDraft] = useState(value)
  const [open, setOpen] = useState(false)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])

  const push = (next, immediate) => {
    setDraft(next)
    clearTimeout(timer.current)
    if (immediate) onChange(next)
    else timer.current = setTimeout(() => onChange(next), 350)
  }

  const active = countActiveFilters(draft)
  const skillCount = Object.keys(draft.skills).length

  const toggleStatus = (s) => {
    const statuses = draft.statuses.includes(s) ? draft.statuses.filter((x) => x !== s) : [...draft.statuses, s]
    push({ ...draft, statuses }, true)
  }

  const toggleStage = (s) => {
    const stages = draft.stages.includes(s) ? draft.stages.filter((x) => x !== s) : [...draft.stages, s]
    push({ ...draft, stages }, true)
  }

  const cycleSkill = (skill) => {
    const current = draft.skills[skill] ?? null
    const next = SKILL_CYCLE[(SKILL_CYCLE.indexOf(current) + 1) % SKILL_CYCLE.length]
    const skills = { ...draft.skills }
    if (next) skills[skill] = next
    else delete skills[skill]
    push({ ...draft, skills }, true)
  }

  return (
    <div className="mb-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={draft.q}
          onChange={(e) => push({ ...draft, q: e.target.value }, false)}
          placeholder="Search by name, email or file name"
          aria-label="Search applicants"
          className={`${input} min-w-[14rem] flex-1 py-1.5`}
        />
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="rounded border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Filters{active > 0 ? ` (${active})` : ''} {open ? '▴' : '▾'}
        </button>
        {active > 0 && (
          <button type="button" onClick={() => push(EMPTY_FILTERS, true)} className="text-xs font-medium text-slate-600 underline hover:no-underline dark:text-slate-300">
            Clear all
          </button>
        )}
      </div>

      {open && (
        <div className="space-y-4 rounded border border-slate-200 p-3 dark:border-slate-700">
          <div>
            <span className={label}>{mode === 'shortlisted' ? 'Stage' : 'Status'}</span>
            <div className="flex flex-wrap gap-1.5">
              {(mode === 'shortlisted' ? SHORTLIST_STAGE_OPTIONS : APPLICATION_STATUS_OPTIONS).map((s) => {
                const on = (mode === 'shortlisted' ? draft.stages : draft.statuses).includes(s)
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => (mode === 'shortlisted' ? toggleStage(s) : toggleStatus(s))}
                    aria-pressed={on}
                    className={`rounded-full border px-2.5 py-0.5 text-xs ${on ? 'border-indigo-400 bg-indigo-50 text-indigo-800 dark:border-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300' : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'}`}
                  >
                    {mode === 'shortlisted' ? stageLabel(s) : statusLabel(s)}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="flex flex-wrap gap-6">
            <div>
              <span className={label}>AI score (%)</span>
              <div className="flex items-center gap-1.5">
                <input type="number" min="0" max="100" placeholder="Min" value={draft.minScore} onChange={(e) => push({ ...draft, minScore: e.target.value }, false)} className={`${input} w-16`} aria-label="Minimum AI score" />
                <span className="text-xs text-slate-400">to</span>
                <input type="number" min="0" max="100" placeholder="Max" value={draft.maxScore} onChange={(e) => push({ ...draft, maxScore: e.target.value }, false)} className={`${input} w-16`} aria-label="Maximum AI score" />
              </div>
            </div>
            <div>
              <span className={label}>Experience (years)</span>
              <div className="flex items-center gap-1.5">
                <input type="number" min="0" step="0.5" placeholder="Min" value={draft.minYears} onChange={(e) => push({ ...draft, minYears: e.target.value }, false)} className={`${input} w-16`} aria-label="Minimum years of experience" />
                <span className="text-xs text-slate-400">to</span>
                <input type="number" min="0" step="0.5" placeholder="Max" value={draft.maxYears} onChange={(e) => push({ ...draft, maxYears: e.target.value }, false)} className={`${input} w-16`} aria-label="Maximum years of experience" />
              </div>
            </div>
            <div>
              <span className={label}>Any skill on the resume</span>
              <input type="text" placeholder="e.g. kubernetes" value={draft.resumeSkill} onChange={(e) => push({ ...draft, resumeSkill: e.target.value }, false)} className={`${input} w-44`} aria-label="Search resume skills" />
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className={label.replace('mb-1 ', '')}>Job skills</span>
              {skillCount > 1 && (
                <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                  Match
                  {['all', 'any'].map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => push({ ...draft, skillMode: m }, true)}
                      aria-pressed={draft.skillMode === m}
                      className={`rounded px-1.5 py-0.5 ${draft.skillMode === m ? 'bg-slate-200 font-medium text-slate-800 dark:bg-slate-700 dark:text-slate-100' : ''}`}
                    >
                      {m}
                    </button>
                  ))}
                  selected
                </div>
              )}
            </div>
            {jdSkills.length === 0 ? (
              <p className="text-xs text-slate-400 dark:text-slate-500">This job has no extracted skills yet.</p>
            ) : (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {jdSkills.map((skill) => {
                    const mode = draft.skills[skill]
                    return (
                      <button
                        key={skill}
                        type="button"
                        onClick={() => cycleSkill(skill)}
                        title="Click to cycle: has → proven → missing → off"
                        className={`rounded-full border px-2.5 py-0.5 text-xs ${mode ? SKILL_STYLE[mode] : 'border-dashed border-slate-300 text-slate-600 dark:border-slate-600 dark:text-slate-300'}`}
                      >
                        {skill}{mode ? ` · ${SKILL_LABEL[mode]}` : ''}
                      </button>
                    )
                  })}
                </div>
                <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">
                  Click a skill to cycle: <b>has</b> (on the resume), <b>proven</b> (shown in a job or project, not just listed), <b>missing</b>.
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
