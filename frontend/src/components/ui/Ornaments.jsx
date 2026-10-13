import { useId } from 'react'

// Decorative vector art. Everything here is aria-hidden, inline SVG, and
// colours itself with currentColor / the theme's gold, so it follows light and
// dark mode and needs no image files.

const uid = (raw) => raw.replace(/[^a-zA-Z0-9]/g, '')

/** The TalentMatch crest: a gold-trimmed shield bearing a "T". */
export function Crest({ className = 'h-9 w-9' }) {
  const id = uid(useId())
  return (
    <svg viewBox="0 0 40 44" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ecdcae" />
          <stop offset="1" stopColor="#b58c3e" />
        </linearGradient>
        <linearGradient id={`${id}f`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#24366a" />
          <stop offset="1" stopColor="#121b38" />
        </linearGradient>
      </defs>
      <path
        d="M20 2 36 8.5v14.2c0 9.6-6.6 15.4-16 19.3C10.6 38.100 4 32.300 4 22.700V8.500Z"
        fill={`url(#${id}f)`}
        stroke={`url(#${id}g)`}
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M20 6.200 32.400 11v11.500c0 7.400-5.100 12-12.400 15.400-7.300-3.400-12.400-8-12.400-15.400V11Z"
        fill="none"
        stroke={`url(#${id}g)`}
        strokeWidth=".6"
        opacity=".7"
      />
      <path d="M13 15h14M20 15v14" stroke={`url(#${id}g)`} strokeWidth="2.6" strokeLinecap="round" />
      <path d="M16.500 29h7" stroke={`url(#${id}g)`} strokeWidth="1.200" strokeLinecap="round" opacity=".8" />
      <circle cx="20" cy="9.800" r="1" fill={`url(#${id}g)`} />
    </svg>
  )
}

/** Hairline divider with a centred diamond. Colour comes from `text-*`. */
export function Flourish({ className = 'h-4 w-52' }) {
  const id = uid(useId())
  return (
    <svg viewBox="0 0 240 16" className={className} aria-hidden="true" fill="none">
      <defs>
        <linearGradient id={`${id}l`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="currentColor" stopOpacity="0" />
          <stop offset="1" stopColor="currentColor" stopOpacity="1" />
        </linearGradient>
        <linearGradient id={`${id}r`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="currentColor" stopOpacity="1" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M4 8h96" stroke={`url(#${id}l)`} strokeWidth="1" />
      <path d="M140 8h96" stroke={`url(#${id}r)`} strokeWidth="1" />
      <path d="M120 2.500 125.500 8 120 13.500 114.500 8Z" fill="currentColor" />
      <path d="M120 5.500 122.500 8 120 10.500 117.500 8Z" className="fill-slate-50 dark:fill-slate-950" />
      <circle cx="106" cy="8" r="1.600" fill="currentColor" />
      <circle cx="134" cy="8" r="1.600" fill="currentColor" />
    </svg>
  )
}

/**
 * Art-deco sunburst that fans down from the top edge of every page:
 * concentric arcs, radiating rays and a ring of small diamonds.
 */
export function DecoBackdrop() {
  const rays = Array.from({ length: 21 }, (_, i) => {
    const a = (Math.PI * (12 + i * 7.8)) / 180 // fan from 12deg to 168deg
    const len = i % 2 === 0 ? 470 : 360
    return { x: 600 + len * Math.cos(a), y: len * Math.sin(a), long: i % 2 === 0 }
  })
  const arcs = [90, 150, 215, 285, 360, 440]
  const diamonds = Array.from({ length: 13 }, (_, i) => {
    const a = (Math.PI * (24 + i * 11)) / 180
    return { x: 600 + 318 * Math.cos(a), y: 318 * Math.sin(a) }
  })

  return (
    <div
      aria-hidden="true"
      className="deco-backdrop pointer-events-none absolute inset-x-0 top-0 h-[30rem] overflow-hidden text-gold-500 opacity-[0.22] dark:text-gold-400 dark:opacity-[0.18]"
    >
      <svg
        viewBox="0 0 1200 480"
        preserveAspectRatio="xMidYMin slice"
        className="absolute left-1/2 top-0 h-full min-w-[1200px] -translate-x-1/2"
        fill="none"
        stroke="currentColor"
      >
        {arcs.map((r, i) => (
          <path
            key={r}
            d={`M${600 - r} 0A${r} ${r} 0 0 0 ${600 + r} 0`}
            strokeWidth={i % 2 ? 0.6 : 1}
            strokeDasharray={i === 2 ? '2 6' : undefined}
          />
        ))}
        {rays.map((r, i) => (
          <path key={i} d={`M600 0L${r.x.toFixed(1)} ${r.y.toFixed(1)}`} strokeWidth={r.long ? 0.8 : 0.5} />
        ))}
        {diamonds.map((d, i) => (
          <path
            key={i}
            d={`M${d.x.toFixed(1)} ${(d.y - 5).toFixed(1)}l4 5-4 5-4-5Z`}
            fill="currentColor"
            stroke="none"
          />
        ))}
        <path d="M0 0V0" />
      </svg>
    </div>
  )
}

/** Quarter-fan of arcs and rays for the corners of the sign-in screens. */
export function CornerFan({ className = '' }) {
  const rays = Array.from({ length: 9 }, (_, i) => {
    const a = (Math.PI / 2) * (i / 8)
    return { x: 300 * Math.cos(a), y: 300 * Math.sin(a) }
  })
  return (
    <svg viewBox="0 0 300 300" className={className} aria-hidden="true" fill="none" stroke="currentColor">
      {[60, 105, 150, 200, 250, 298].map((r, i) => (
        <path key={r} d={`M${r} 0A${r} ${r} 0 0 1 0 ${r}`} strokeWidth={i % 2 ? 0.7 : 1.2} />
      ))}
      {rays.map((r, i) => (
        <path key={i} d={`M0 0L${r.x.toFixed(1)} ${r.y.toFixed(1)}`} strokeWidth="0.7" />
      ))}
    </svg>
  )
}

const ART = {
  // briefcase
  jobs: (
    <>
      <rect x="22" y="34" width="52" height="34" rx="4" />
      <path d="M38 34v-5a4 4 0 0 1 4-4h12a4 4 0 0 1 4 4v5" />
      <path d="M22 50h52" />
      <rect x="43" y="46" width="10" height="9" rx="1.500" className="fill-slate-50 dark:fill-slate-900" />
    </>
  ),
  // stack of documents
  resumes: (
    <>
      <path d="M30 28h30a3 3 0 0 1 3 3v37a3 3 0 0 1-3 3H33a3 3 0 0 1-3-3Z" opacity=".5" transform="translate(-6 -2)" />
      <path d="M36 24h30a3 3 0 0 1 3 3v41a3 3 0 0 1-3 3H39a3 3 0 0 1-3-3Z" className="fill-slate-50 dark:fill-slate-900" />
      <path d="M43 38h20M43 46h20M43 54h12" />
      <circle cx="53" cy="31" r="0" />
    </>
  ),
  // open ledger
  history: (
    <>
      <path d="M48 32c-7-5-17-6-26-4v38c9-2 19-1 26 4 7-5 17-6 26-4V28c-9-2-19-1-26 4Z" className="fill-slate-50 dark:fill-slate-900" />
      <path d="M48 32v38" />
      <path d="M29 38c4-1 8-1 12 0M29 46c4-1 8-1 12 0M29 54c4-1 8-1 12 0M55 38c4-1 8-1 12 0M55 46c4-1 8-1 12 0" opacity=".7" />
    </>
  ),
}

/** Soft line-art illustration for empty lists. variant: jobs | resumes | history */
export function EmptyArt({ variant = 'jobs', className = 'mx-auto mb-4 h-24 w-24' }) {
  return (
    <svg viewBox="0 0 96 96" className={`${className} text-gold-500 dark:text-gold-400`} aria-hidden="true" fill="none">
      <circle cx="48" cy="48" r="44" fill="currentColor" opacity=".07" />
      <circle cx="48" cy="48" r="44" stroke="currentColor" strokeWidth=".8" strokeDasharray="1.500 4.500" opacity=".6" />
      <g stroke="currentColor" strokeWidth="1.800" strokeLinecap="round" strokeLinejoin="round">
        {ART[variant]}
      </g>
      <path d="M48 6l2.200 2.200L48 10.400 45.800 8.200Z" fill="currentColor" />
      <path d="M48 85.600l2.200 2.200L48 90l-2.200-2.200Z" fill="currentColor" opacity=".6" />
    </svg>
  )
}
