import Spinner from './Spinner'

// Shown while the app finds out whether the browser already has a live login.
export default function FullPageSpinner() {
  return (
    <div className="app-bg flex min-h-screen items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
}
