function csvCell(value) {
  if (value === null || value === undefined) return ''
  let text = value instanceof Date ? value.toISOString() : String(value)
  // Prevent spreadsheet formula injection from user-controlled text fields.
  if (/^[\s]*[=+@]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function downloadCsv(filename, rows, columns) {
  if (!Array.isArray(rows) || rows.length === 0) return false
  const keys = columns ?? [...new Set(rows.flatMap((row) => Object.keys(row ?? {})))]
  const content = [keys.map(csvCell).join(','), ...rows.map((row) => keys.map((key) => csvCell(row?.[key])).join(','))].join('\r\n')
  const blob = new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
  return true
}
