// Minimal JWT payload decoder — we only ever need to read claims
// (role, sub, exp) client-side, never verify the signature (the
// backend does that on every request), so no library is needed.
export function decodeJwtPayload(token) {
  try {
    const payload = token.split('.')[1]
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decoded)
  } catch {
    return null
  }
}

export function isTokenExpired(payload) {
  if (!payload?.exp) return true
  // exp is seconds since epoch; Date.now() is milliseconds
  return Date.now() >= payload.exp * 1000
}