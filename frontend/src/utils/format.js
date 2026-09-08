// Sentence-case for enum values coming from the API: "full_time" -> "Full time"
export function formatEnumLabel(value) {
  if (!value) return null
  const words = String(value).replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}