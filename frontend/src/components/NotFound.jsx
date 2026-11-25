// For pages a user may not open (e.g. org pages without access, T-166). No
// redirect: switching accounts mid-page would race with the next navigation.
export default function NotFound() {
  return <p className="text-slate-600">Page not found.</p>
}
