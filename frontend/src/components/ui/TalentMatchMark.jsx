import { Flourish } from './Ornaments'

// TalentMatch brand system. Three variants share one design language so the
// name looks identical everywhere it appears:
//   <TalentMatchWordmark />  big lockup for sign-in / register
//   <TalentMatchEyebrow />   small tracked label above page titles
//   <TalentMatchFooter />    quiet signature at the bottom of every page
// Everything is inline SVG + text, follows light/dark via the theme tokens.

/** Two interlocking diamonds: a "match". */
export function MatchGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
      <path d="M8.500 3 14 8.500 8.500 14 3 8.500Z" className="text-indigo-600 dark:text-indigo-300" />
      <path d="M15.500 10 21 15.500 15.500 21 10 15.500Z" className="text-gold-500 dark:text-gold-400" />
    </svg>
  )
}

export function TalentMatchWordmark({ className = '' }) {
  return (
    <div className={`flex flex-col items-center ${className}`} role="img" aria-label="TalentMatch">
      <div className="flex items-center gap-2" aria-hidden="true">
        <MatchGlyph className="h-6 w-6" />
        <span className="font-display text-[1.7rem] font-semibold leading-none tracking-tight text-slate-900 dark:text-slate-100">
          Talent<span className="text-gold-600 dark:text-gold-400">Match</span>
        </span>
      </div>
      <Flourish className="mt-2 h-3 w-40 text-gold-500/80 dark:text-gold-400/60" />
    </div>
  )
}

export function TalentMatchEyebrow({ section, className = '' }) {
  return (
    <p className={`mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] ${className}`}>
      <MatchGlyph className="h-3.5 w-3.5" />
      <span className="text-slate-900 dark:text-slate-100">TalentMatch</span>
      {section && <>
        <span aria-hidden="true" className="h-3 w-px bg-gold-400/70 dark:bg-gold-400/50" />
        <span className="text-indigo-600 dark:text-indigo-300">{section}</span>
      </>}
    </p>
  )
}

export function TalentMatchFooter() {
  return (
    <footer className="relative mx-auto max-w-[1440px] px-6 pb-10 pt-6 text-center" aria-hidden="true">
      <Flourish className="mx-auto h-4 w-52 text-gold-500/70 dark:text-gold-400/50" />
      <p className="mt-2 flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-[0.35em] text-slate-400 dark:text-slate-600">
        <MatchGlyph className="h-3.5 w-3.5 opacity-70" />TalentMatch
      </p>
    </footer>
  )
}
