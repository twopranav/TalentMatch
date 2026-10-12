import { formatExperienceMonths } from '../../utils/format'

const SOURCE_LABEL = {
  work_experience: 'Work experience',
  projects: 'Projects',
  skills_section: 'Skills section',
}

const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)

function Bar({ value, tone = 'bg-indigo-500' }) {
  const width = Math.max(0, Math.min(1, value ?? 0)) * 100
  return (
    <div className="h-1.5 w-full rounded bg-slate-200 dark:bg-slate-700">
      <div className={`h-1.5 rounded ${tone}`} style={{ width: `${width}%` }} />
    </div>
  )
}

function Factor({ name, value, help }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="font-medium text-slate-700 dark:text-slate-200">{name}</span>
        <span className="tabular-nums text-slate-600 dark:text-slate-300">{pct(value)}</span>
      </div>
      <Bar value={value} />
      <p className="mt-0.5 text-slate-500 dark:text-slate-400">{help}</p>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">{title}</h4>
      {children}
    </section>
  )
}

// Everything the matcher stored in match_details, laid out so a recruiter can
// answer "why this number?": how the final score is built, how the skills
// score is built, what happened to each job skill, and the experience part.
// Older rows may lack some fields, so every number is optional.
export default function ScoreExplanation({ details }) {
  if (!details) return null
  const matched = details.matched || []
  const missing = details.missing || []
  const w = details.weights_used || {}
  const hasWeights = w.skills != null && w.experience != null
  const skillsPts = hasWeights && details.skills_score != null ? 100 * w.skills * details.skills_score : null
  const expPts = hasWeights && details.experience_score != null ? 100 * w.experience * details.experience_score : null
  const total = details.score
  const noJdSkills = matched.length + missing.length === 0

  const have = formatExperienceMonths(details.resume_months)
  const need = formatExperienceMonths(details.jd_min_months)
  const proven = matched.filter((m) => m.status === 'proven').length

  return (
    <div className="space-y-5 text-xs text-slate-600 dark:text-slate-300">
      <Section title="How the final score is built">
        {noJdSkills ? (
          <p>The job description has no skills listed, so there is nothing to match this resume against and the score is 0.</p>
        ) : (
          <>
            <p>
              Final score = skills × {hasWeights ? pct(w.skills) : 'its weight'} + experience × {hasWeights ? pct(w.experience) : 'its weight'}
              {total != null ? <> = <b className="tabular-nums">{Math.round(total)}%</b></> : null}
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <div className="flex justify-between">
                  <span className="font-medium text-slate-700 dark:text-slate-200">Skills score</span>
                  <span className="tabular-nums">{pct(details.skills_score)}{skillsPts != null ? ` → ${skillsPts.toFixed(1)} pts` : ''}</span>
                </div>
                <Bar value={details.skills_score} tone="bg-emerald-500" />
              </div>
              <div>
                <div className="flex justify-between">
                  <span className="font-medium text-slate-700 dark:text-slate-200">Experience score</span>
                  <span className="tabular-nums">{pct(details.experience_score)}{expPts != null ? ` → ${expPts.toFixed(1)} pts` : ''}</span>
                </div>
                <Bar value={details.experience_score} tone="bg-amber-500" />
              </div>
            </div>
          </>
        )}
      </Section>

      {!noJdSkills && (
        <Section title="How the skills score is built">
          <p>
            {matched.length} of {matched.length + missing.length} job skills found ({proven} proven, {matched.length - proven} only mentioned), {missing.length} missing. Three measures are blended into the skills score:
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Factor name="Coverage" value={details.coverage} help="How much of the job's skill list the resume covers, with partial credit for close matches." />
            <Factor name="Proof rate" value={details.proof_rate} help="Share of job skills shown in a job or project, not just listed." />
            <Factor name="Balance" value={details.balance} help="Rewards covering skills evenly; a few strong skills with many gaps scores lower." />
          </div>
          {details.skills_basis === 'flat_fallback' && (
            <p className="rounded bg-amber-50 px-2 py-1 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
              This resume has no per-section skill data, so every skill counted as a plain mention (lowest weight). Re-extracting the resume may raise the score.
            </p>
          )}
        </Section>
      )}

      {!noJdSkills && (
        <Section title="Each job skill">
          <div className="overflow-x-auto rounded border border-slate-200 dark:border-slate-700">
            <table className="w-full text-left">
              <thead className="bg-slate-50 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                <tr>
                  <th className="px-2 py-1.5 font-medium">Job skill</th>
                  <th className="px-2 py-1.5 font-medium">Result</th>
                  <th className="px-2 py-1.5 font-medium">Found on resume as</th>
                  <th className="px-2 py-1.5 font-medium">Where</th>
                  <th className="px-2 py-1.5 font-medium">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {matched.map((m) => {
                  const isProven = m.status === 'proven'
                  const exact = !m.resume_skill || m.resume_skill === m.jd_skill
                  return (
                    <tr key={m.jd_skill} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="px-2 py-1.5 font-medium text-slate-700 dark:text-slate-200">{m.jd_skill}</td>
                      <td className="px-2 py-1.5">
                        <span className={`rounded px-1.5 py-0.5 ${isProven ? 'bg-indigo-50 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300' : 'bg-emerald-50 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'}`}>
                          {isProven ? 'Proven' : 'Mentioned'}
                        </span>
                      </td>
                      <td className="px-2 py-1.5">{exact ? 'exact match' : `${m.resume_skill} (${pct(m.similarity)} similar)`}</td>
                      <td className="px-2 py-1.5">
                        {SOURCE_LABEL[m.source] || m.source || '—'}
                        {m.tier_weight != null ? <span className="text-slate-400"> · weight {m.tier_weight}</span> : null}
                      </td>
                      <td className="w-28 px-2 py-1.5">
                        <div className="tabular-nums">{pct(m.evidence)}</div>
                        <Bar value={m.evidence} tone={isProven ? 'bg-indigo-500' : 'bg-emerald-500'} />
                      </td>
                    </tr>
                  )
                })}
                {missing.map((s) => (
                  <tr key={s} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-1.5 font-medium text-slate-700 dark:text-slate-200">{s}</td>
                    <td className="px-2 py-1.5"><span className="rounded bg-red-50 px-1.5 py-0.5 text-red-700 dark:bg-red-900/30 dark:text-red-300">Missing</span></td>
                    <td className="px-2 py-1.5 text-slate-400" colSpan={3}>No resume skill is close enough to count.</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-slate-400 dark:text-slate-500">
            Evidence = how closely the resume skill matches × how much its source counts (work experience counts most, then projects, then the skills list).
          </p>
        </Section>
      )}

      <Section title="Experience">
        <p>
          Resume: <b>{have ?? 'not stated'}</b>
          {need ? <> · job asks for <b>{need}</b></> : ' · job states no minimum'}
          {details.meets_min_experience === true && <span className="ml-2 rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">meets minimum</span>}
          {details.meets_min_experience === false && <span className="ml-2 rounded bg-red-50 px-1.5 py-0.5 text-red-700 dark:bg-red-900/30 dark:text-red-300">below minimum</span>}
        </p>
        <p>
          Experience score {pct(details.experience_score)}. It rises with total months worked and levels off toward 100%
          {details.experience_scale_months ? ` (about ${Math.round((1 - Math.exp(-1)) * 100)}% at ${formatExperienceMonths(details.experience_scale_months)})` : ''}, so extra years help less and less. It is not a pass/fail check against the minimum.
        </p>
      </Section>
    </div>
  )
}
