import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { fetchAuditPage } from '../api/audit'
import Pagination from '../components/ui/Pagination'
import Spinner from '../components/ui/Spinner'
import { EmptyArt } from '../components/ui/Ornaments'
import { formatEnumLabel, getErrorMessage } from '../utils/format'
import PageHeader from '../components/ui/PageHeader'
import StatusBadge from '../components/ui/StatusBadge'
import Button from '../components/ui/Button'
import { useToast } from '../components/ui/Toast'
import { downloadCsv } from '../utils/csv'

const PAGE_SIZE = 25


const RESOURCE_LABELS = {
  job: 'Job',
  application: 'Application',
  application_note: 'Application note',
  user: 'User',
  resume: 'Resume',
  llm_config: 'LLM config',
}

// Recruiters only ever receive job-scoped entries from the backend, so only
// offer them the types that can appear.
const RECRUITER_TYPES = ['job', 'application', 'application_note']
const ADMIN_TYPES = [...RECRUITER_TYPES, 'user', 'resume', 'llm_config']

const FILTER_KEYS = ['resource_type', 'action', 'job_id', 'resource_id', 'actor_id', 'date_from', 'date_to']
const CHIP_LABELS = { job_id: 'Job', resource_id: 'Record', actor_id: 'Actor', date_from: 'From', date_to: 'To' }

const selectClass =
  'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200'

const resourceLabel = (type) => RESOURCE_LABELS[type] ?? formatEnumLabel(type)

function formatValue(value) {
  if (value === null || value === undefined) {
    return <span className="italic text-slate-400 dark:text-slate-500">empty</span>
  }
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > 300 ? `${text.slice(0, 300)}…` : text
}

function ChangeDetail({ entry }) {
  const { action, before, after, changed_fields: changed } = entry

  let fields
  if (action === 'update') fields = changed
  else fields = Object.keys((action === 'delete' ? before : after) ?? {}).filter((k) => k !== 'updated_at').sort()

  if (fields.length === 0) {
    return <p className="text-xs text-slate-500 dark:text-slate-400">No field changes were recorded for this entry.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="text-slate-500 dark:text-slate-400">
            <th className="w-1/4 py-1 pr-3 font-medium">Field</th>
            <th className="w-3/8 py-1 pr-3 font-medium">Before</th>
            <th className="py-1 font-medium">After</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field} className="border-t border-slate-200 align-top dark:border-slate-700">
              <td className="py-1.5 pr-3 font-mono text-slate-700 dark:text-slate-300">{field}</td>
              <td className="break-all py-1.5 pr-3 text-slate-600 dark:text-slate-400">
                {action === 'create' ? '—' : formatValue(before?.[field])}
              </td>
              <td className="break-all py-1.5 text-slate-900 dark:text-slate-100">
                {action === 'delete' ? '—' : formatValue(after?.[field])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AuditRow({ entry, expanded, onToggle, onFilter }) {
  const summary =
    entry.action === 'update'
      ? (entry.changed_fields ?? []).length
        ? (entry.changed_fields ?? []).join(', ')
        : 'no field changes'
      : entry.action === 'create'
        ? 'record created'
        : 'record deleted'

  return (
    <div className="border-b border-slate-100 last:border-0 dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={expanded ? 'Hide details' : 'Show details'}
          className="rounded px-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <span className={`inline-block text-xs transition-transform ${expanded ? 'rotate-90' : ''}`}>▶</span>
        </button>

        <span className="w-40 shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">
          {new Date(entry.created_at).toLocaleString()}
        </span>

        <StatusBadge status={entry.action}>{formatEnumLabel(entry.action)}</StatusBadge>

        <div className="min-w-0 flex-1">
          <div className="text-sm text-slate-900 dark:text-slate-100">
            {entry.resource_label || resourceLabel(entry.resource_type)}{' '}
            <button
              type="button"
              onClick={() => onFilter({ resource_id: entry.resource_id })}
              title={`Show history of ${entry.resource_id}`}
              className="font-mono text-xs text-indigo-600 hover:underline dark:text-indigo-400"
            >
              {entry.resource_id.slice(0, 8)}
            </button>
          </div>
          <div className="truncate text-xs text-slate-500 dark:text-slate-400">{summary}</div>
        </div>

        <div className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
          {entry.actor_id ? (
            <button
              type="button"
              onClick={() => onFilter({ actor_id: entry.actor_id })}
              title="Show only this person's actions"
              className="hover:text-slate-800 hover:underline dark:hover:text-slate-200"
            >
              {entry.actor_email ?? entry.actor_id.slice(0, 8)}
            </button>
          ) : (
            <span title="No signed-in user, e.g. a new account registering">{entry.actor_email ?? 'System'}</span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="bg-slate-50 px-4 py-3 pl-12 dark:bg-slate-950/40">
          <ChangeDetail entry={entry} />
        </div>
      )}
    </div>
  )
}

async function fetchAllAuditRows(filters) {
  const serverFilters = { ...filters, date_from: '', date_to: '' }
  const rows = []
  let offset = 0
  let total = Infinity
  const limit = 200
  while (offset < total) {
    const page = await fetchAuditPage(serverFilters, limit, offset)
    rows.push(...page.items)
    total = page.total
    if (!page.items.length) break
    offset += page.items.length
  }
  const from = filters.date_from ? new Date(`${filters.date_from}T00:00:00`).getTime() : -Infinity
  const to = filters.date_to ? new Date(`${filters.date_to}T23:59:59.999`).getTime() : Infinity
  return rows.filter((entry) => {
    const time = new Date(entry.created_at).getTime()
    return time >= from && time <= to
  })
}

export default function AuditHistory() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const isAdmin = user?.role === 'admin' || user?.role === 'superuser'
  const resourceTypes = isAdmin ? ADMIN_TYPES : RECRUITER_TYPES

  // Filters live in the URL so a view can be linked to / bookmarked, and so
  // other pages can deep-link here (e.g. ?job_id=... from My Jobs).
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, searchParams.get(k) ?? '']))
  const filterSignature = FILTER_KEYS.map((k) => filters[k]).join('|')
  const [actorDraft, setActorDraft] = useState(filters.actor_id)
  useEffect(() => setActorDraft(filters.actor_id), [filters.actor_id])

  const [page, setPage] = useState(1)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [exporting, setExporting] = useState(false)
  const requestId = useRef(0)

  const load = useCallback(() => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    const hasDateFilter = Boolean(filters.date_from || filters.date_to)
    const serverFilters = { ...filters, date_from: '', date_to: '' }
    const request = hasDateFilter
      ? fetchAllAuditRows(filters).then((rows) => ({ items: rows, total: rows.length, allRowsLoaded: true }))
      : fetchAuditPage(serverFilters, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    request.then(({ items: rows, total: count, allRowsLoaded }) => {
      if (id !== requestId.current) return
      setItems(rows)
      setTotal(count)
      if (allRowsLoaded && page > Math.max(1, Math.ceil(count / PAGE_SIZE))) setPage(Math.max(1, Math.ceil(count / PAGE_SIZE)))
    }).catch((err) => {
      if (id !== requestId.current) return
      setItems([])
      setTotal(0)
      setError(getErrorMessage(err, 'Could not load the audit history. Please try again.'))
    }).finally(() => {
      if (id === requestId.current) setLoading(false)
    })
    // filters are tracked by a stable signature so URL-backed controls drive this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterSignature, page])

  useEffect(() => {
    load()
  }, [load])

  const updateFilters = (changes) => {
    const next = new URLSearchParams(searchParams)
    Object.entries(changes).forEach(([key, value]) => {
      if (value) next.set(key, value)
      else next.delete(key)
    })
    setSearchParams(next)
    setPage(1)
    setExpandedId(null)
  }

  const exportCsv = async () => {
    setExporting(true)
    try {
      const rows = await fetchAllAuditRows(filters)
      const count = downloadCsv('talentmatch-audit-history', rows.map((entry) => ({
        timestamp: entry.created_at,
        actor_email: entry.actor_email ?? '',
        actor_id: entry.actor_id ?? '',
        action: entry.action,
        resource_type: entry.resource_type,
        resource_label: entry.resource_label ?? resourceLabel(entry.resource_type),
        resource_id: entry.resource_id,
        changed_fields: (entry.changed_fields ?? []).join('; '),
        before: entry.before ? JSON.stringify(entry.before) : '',
        after: entry.after ? JSON.stringify(entry.after) : '',
      })))
      showToast(count ? `Exported ${rows.length} audit entries.` : 'No audit entries to export.', count ? 'success' : 'info')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not export audit history.'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const activeChips = ['job_id', 'resource_id', 'actor_id'].filter((k) => filters[k])
  const hasFilters = FILTER_KEYS.some((k) => filters[k])
  const dateRangeActive = Boolean(filters.date_from || filters.date_to)
  const visibleItems = dateRangeActive ? items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE) : items

  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      <PageHeader eyebrow="Activity & governance" title="Audit history" description={isAdmin ? 'Review changes made across the platform, newest first.' : 'Review changes to your jobs, applications, and notes.'} action={<Button variant="secondary" onClick={exportCsv} disabled={exporting || loading}>{exporting ? 'Exporting…' : 'Export CSV ↓'}</Button>} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          aria-label="Filter by record type"
          value={filters.resource_type}
          onChange={(e) => updateFilters({ resource_type: e.target.value })}
          className={selectClass}
        >
          <option value="">All record types</option>
          {resourceTypes.map((t) => (
            <option key={t} value={t}>{resourceLabel(t)}</option>
          ))}
        </select>

        <select
          aria-label="Filter by action"
          value={filters.action}
          onChange={(e) => updateFilters({ action: e.target.value })}
          className={selectClass}
        >
          <option value="">All actions</option>
          <option value="create">Created</option>
          <option value="update">Updated</option>
          <option value="delete">Deleted</option>
        </select>

        <label className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400">From
          <input type="date" aria-label="Audit start date" value={filters.date_from} max={filters.date_to || undefined} onChange={(event) => updateFilters({ date_from: event.target.value })} className={selectClass} />
        </label>
        <label className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400">To
          <input type="date" aria-label="Audit end date" value={filters.date_to} min={filters.date_from || undefined} onChange={(event) => updateFilters({ date_to: event.target.value })} className={selectClass} />
        </label>
        <form onSubmit={(event) => { event.preventDefault(); updateFilters({ actor_id: actorDraft.trim() }) }} className="flex items-center gap-2">
          <label htmlFor="audit-actor-filter" className="sr-only">Filter by actor ID</label>
          <input id="audit-actor-filter" aria-label="Filter by actor ID" value={actorDraft} onChange={(event) => setActorDraft(event.target.value)} placeholder="Actor UUID" className={`${selectClass} w-52`} />
          <Button type="submit" variant="secondary" size="sm">Apply actor</Button>
        </form>

        {activeChips.map((key) => (
          <span
            key={key}
            className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 py-1 pl-3 pr-1.5 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-100 dark:bg-indigo-500/15 dark:text-indigo-300 dark:ring-indigo-500/20"
          >
            {CHIP_LABELS[key]}: <span className="font-mono">{filters[key].slice(0, 8)}</span>
            <button
              type="button"
              onClick={() => updateFilters({ [key]: '' })}
              aria-label={`Clear ${CHIP_LABELS[key].toLowerCase()} filter`}
              className="rounded-full px-1 leading-none opacity-60 hover:opacity-100"
            >
              ×
            </button>
          </span>
        ))}

        {hasFilters && (
          <button
            type="button"
            onClick={() => updateFilters(Object.fromEntries(FILTER_KEYS.map((k) => [k, ''])))}
            className="text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
          >
            Clear all
          </button>
        )}

        {!loading && !error && (
          <span className="ml-auto text-xs text-slate-500 dark:text-slate-400">
            {total} {total === 1 ? 'entry' : 'entries'}
          </span>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-3 text-sm text-red-600 dark:text-red-400">
          <span>{error}</span>
          <button type="button" onClick={load} className="font-medium underline">Retry</button>
        </div>
      )}

      {loading && items.length === 0 && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading audit history" />
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700">
          <EmptyArt variant="history" />
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {hasFilters ? 'No entries match these filters.' : 'Nothing has been recorded yet.'}
          </p>
        </div>
      )}

      {visibleItems.length > 0 && (
        <div
          className={`overflow-hidden rounded-lg border border-slate-200 bg-white transition-opacity dark:border-slate-800 dark:bg-slate-900 ${
            loading ? 'opacity-60' : ''
          }`}
        >
          {visibleItems.map((entry) => (
            <AuditRow
              key={entry.id}
              entry={entry}
              expanded={expandedId === entry.id}
              onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
              onFilter={updateFilters}
            />
          ))}
        </div>
      )}

      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={(p) => {
          setPage(p)
          setExpandedId(null)
        }}
        disabled={loading}
      />
    </div>
  )
}
