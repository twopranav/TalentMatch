import { useRef, useState } from 'react'

export default function FilePicker({ files = [], onChange, accept, multiple = false, disabled = false, label }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const buttonLabel = label ?? (multiple ? 'Choose files' : 'Choose file')
  const addFiles = (picked) => {
    if (!multiple && picked.length) { onChange(picked.slice(0, 1)); return }
    const merged = [...files]
    const seen = new Set(merged.map((file) => `${file.name}:${file.size}:${file.lastModified}`))
    for (const file of picked) {
      const key = `${file.name}:${file.size}:${file.lastModified}`
      if (!seen.has(key)) { seen.add(key); merged.push(file) }
    }
    onChange(merged)
  }
  const handleChange = (event) => { addFiles(Array.from(event.target.files ?? [])); event.target.value = '' }
  const handleDrop = (event) => {
    event.preventDefault(); setDragging(false)
    if (disabled) return
    const picked = Array.from(event.dataTransfer.files ?? [])
    const accepted = accept ? picked.filter((file) => accept.split(',').some((extension) => extension.trim().startsWith('.') && file.name.toLowerCase().endsWith(extension.trim().toLowerCase()))) : picked
    addFiles(accepted)
  }
  return <div onDragEnter={(e) => { e.preventDefault(); if (!disabled) setDragging(true) }} onDragOver={(e) => e.preventDefault()} onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false) }} onDrop={handleDrop} className={`flex flex-wrap items-center gap-3 rounded-xl border border-dashed px-4 py-3 ${dragging ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40' : 'border-slate-300 dark:border-slate-700'}`}>
    <input ref={inputRef} type="file" accept={accept} multiple={multiple} onChange={handleChange} disabled={disabled} aria-label={buttonLabel} className="hidden" />
    <button type="button" onClick={() => inputRef.current?.click()} disabled={disabled} className="rounded-lg bg-indigo-700 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-800 disabled:opacity-60">{buttonLabel}</button>
    <span className="text-xs text-slate-500 dark:text-slate-400">or drag and drop {multiple ? 'files' : 'a file'} here</span>
    {files.length > 0 && <div className="w-full text-xs text-slate-500 dark:text-slate-400">{files.length === 1 ? files[0].name : `${files.length} files selected`}</div>}
  </div>
}
