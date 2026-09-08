// frontend/src/components/jobs/JobFilterBar.jsx
const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'contract', 'internship']
const SENIORITY_LEVELS = ['entry', 'mid', 'senior', 'lead', 'executive']
const REMOTE_TYPES = ['onsite', 'remote', 'hybrid']

function formatLabel(value) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const FIELD_CLASSES =
  'w-40 rounded border border-slate-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500'

export default function JobFilterBar({ filters, onChange }) {
  const update = (field, value) => {
    onChange({ ...filters, [field]: value })
  }

  const clearAll = () => {
    onChange({
      ...filters,
      location: '',
      department: '',
      employment_type: '',
      seniority: '',
      remote_type: '',
    })
  }

  const hasActiveFilters =
    filters.location || filters.department || filters.employment_type || filters.seniority || filters.remote_type

  return (
    <div className="mb-6 flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500 dark:text-slate-400" htmlFor="filter-location">Location</label>
        <input
          id="filter-location"
          type="text"
          placeholder="Any location"
          value={filters.location || ''}
          onChange={(e) => update('location', e.target.value)}
          className={FIELD_CLASSES}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500 dark:text-slate-400" htmlFor="filter-department">Department</label>
        <input
          id="filter-department"
          type="text"
          placeholder="Any department"
          value={filters.department || ''}
          onChange={(e) => update('department', e.target.value)}
          className={FIELD_CLASSES}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500 dark:text-slate-400" htmlFor="filter-employment-type">Employment type</label>
        <select
          id="filter-employment-type"
          value={filters.employment_type || ''}
          onChange={(e) => update('employment_type', e.target.value)}
          className={`w-36 ${FIELD_CLASSES.replace('w-40', '')}`}
        >
          <option value="">Any type</option>
          {EMPLOYMENT_TYPES.map((v) => (
            <option key={v} value={v}>{formatLabel(v)}</option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500 dark:text-slate-400" htmlFor="filter-seniority">Seniority</label>
        <select
          id="filter-seniority"
          value={filters.seniority || ''}
          onChange={(e) => update('seniority', e.target.value)}
          className={`w-32 ${FIELD_CLASSES.replace('w-40', '')}`}
        >
          <option value="">Any level</option>
          {SENIORITY_LEVELS.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500 dark:text-slate-400" htmlFor="filter-remote-type">Remote</label>
        <select
          id="filter-remote-type"
          value={filters.remote_type || ''}
          onChange={(e) => update('remote_type', e.target.value)}
          className={`w-32 ${FIELD_CLASSES.replace('w-40', '')}`}
        >
          <option value="">Any</option>
          {REMOTE_TYPES.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>

      {hasActiveFilters && (
        <button
          onClick={clearAll}
          className="rounded px-3 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          Clear filters
        </button>
      )}
    </div>
  )
}