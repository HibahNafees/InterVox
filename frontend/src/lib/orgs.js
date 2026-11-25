// Organizations (T-166). `user.orgs` comes from /auth/me only for accounts the
// backend lets use the feature (ORG_FEATURE); for everyone else it is missing,
// and nothing org-related renders or calls the API.

export function hasOrgs(user) {
  return Array.isArray(user?.orgs)
}

export function staffOrg(user) {
  return (user?.orgs ?? []).find((o) => o.role === 'coach' || o.role === 'admin') ?? null
}

export function candidateOrgs(user) {
  return (user?.orgs ?? []).filter((o) => o.role === 'candidate')
}

// The org's primary color for accents, or the app's own brand color.
export function brandStyle(org) {
  return org?.color ? { '--org': org.color } : { '--org': 'var(--color-brand-500)' }
}

export const STATUS_LABELS = {
  todo: 'To do',
  in_progress: 'In progress',
  done: 'Done',
  overdue: 'Overdue',
}

export function fmtDate(iso) {
  if (!iso) return ''
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}
