// frontend/src/components/ui/FilePicker.jsx
import { useRef } from 'react'

/**
 * Replaces the browser's native <input type="file"> (and its "No file chosen"
 * text) with a regular button. The chosen file name(s) appear beside it only
 * once something is selected.
 *
 * Props
 *   files      File[]                  current selection (controlled by parent)
 *   onChange   (files: File[]) => void
 *   accept     string                  e.g. ".pdf,.docx"
 *   multiple   boolean
 *   disabled   boolean
 *   label      string                  button text
 */
export default function FilePicker({ files = [], onChange, accept, multiple = false, disabled = false, label }) {
  const inputRef = useRef(null)
  const buttonLabel = label ?? (multiple ? 'Choose files' : 'Choose file')

  const handleChange = (e) => {
    const picked = Array.from(e.target.files ?? [])
    e.target.value = '' // lets the same file be picked again later
    onChange(picked)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <input ref={inputRef} type="file" accept={accept} multiple={multiple} onChange={handleChange} className="hidden" />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
      >
        {buttonLabel}
      </button>
      {files.length > 0 && (
        <span className="max-w-xs truncate text-sm text-slate-500 dark:text-slate-400">
          {files.length === 1 ? files[0].name : `${files.length} files selected`}
        </span>
      )}
    </div>
  )
}
