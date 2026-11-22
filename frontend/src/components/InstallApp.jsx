import { useInstallPrompt } from '../lib/pwa'
import { useDialogs } from './ConfirmDialog'

// "Install app" in the header when the browser offers it (Chrome, Edge, Android);
// on iPhone/iPad, where there is no prompt, the button explains Add to Home Screen.
export default function InstallApp() {
  const { mode, install, dismiss } = useInstallPrompt()
  const { notify } = useDialogs()
  if (!mode) return null
  return (
    <span className="flex items-center">
      <button
        type="button"
        onClick={() =>
          mode === 'prompt' ? install() : notify('To install InterVox: tap Share, then Add to Home Screen.')
        }
        className="rounded-l-full px-3 py-1.5 text-sm font-medium text-brand-700 ring-1 ring-line hover:bg-surface"
      >
        <span aria-hidden="true">⬇ </span>Install app
      </button>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Not now"
        title="Not now"
        className="rounded-r-full px-2 py-1.5 text-sm text-slate-500 ring-1 ring-line hover:bg-surface"
      >
        <span aria-hidden="true">✕</span>
      </button>
    </span>
  )
}
