import { lazy, Suspense, useEffect, useState } from 'react'
import { RUNNABLE, runCode, stopRun } from '../lib/runner'
import { useTheme } from '../lib/theme'
import { useSmallScreen } from '../lib/useSmallScreen'

// Monaco loads on first use, so other pages stay small.
const Editor = lazy(() => import('../lib/monaco'))

const LANGUAGES = [
  ['python', 'Python'],
  ['javascript', 'JavaScript'],
  ['typescript', 'TypeScript'],
  ['java', 'Java'],
  ['csharp', 'C#'],
  ['cpp', 'C++'],
  ['go', 'Go'],
  ['ruby', 'Ruby'],
  ['kotlin', 'Kotlin'],
  ['swift', 'Swift'],
  ['sql', 'SQL'],
  ['plaintext', 'Plain text'],
]

function PlainBox({ value, onChange }) {
  return (
    <textarea
      aria-label="Your code"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      spellCheck={false}
      rows={14}
      className="field font-mono text-sm"
    />
  )
}

// Run button and output. The last run's output is kept on `code` (output, ran)
// so it goes with the answer while the code is unchanged since that run.
function RunPanel({ code, onChange }) {
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('')
  const [live, setLive] = useState('')
  const [result, setResult] = useState(null)
  useEffect(() => stopRun, [])
  const runnable = RUNNABLE[code.language]
  const stale = result && code.ran !== code.content

  async function run() {
    setRunning(true)
    setResult(null)
    setLive('')
    const res = await runCode(code.language, code.content, { onStatus: setStatus, onOutput: setLive })
    setRunning(false)
    setStatus('')
    setResult(res)
    const note = res.timedOut
      ? '\n[Stopped after 5 seconds: is there an endless loop?]'
      : res.stopped
        ? '\n[Stopped]'
        : ''
    const output = `${res.output}${res.error ? `${res.error}\n` : ''}${note}`.trim() || '(no output)'
    onChange({ ...code, output: output.slice(0, 4000), ran: code.content })
  }

  if (!runnable) {
    return (
      <p className="text-xs text-slate-500">
        Run works for Python and JavaScript. For this language, talk through what your code would print.
      </p>
    )
  }
  const shown = running ? live : result ? code.output : ''
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        {running ? (
          <button type="button" onClick={stopRun} className="btn-secondary">
            <span aria-hidden="true">■</span> Stop
          </button>
        ) : (
          <button type="button" onClick={run} disabled={!code.content.trim()} className="btn-secondary">
            <span aria-hidden="true">▶</span> Run
          </button>
        )}
        <span className="text-xs text-slate-500">
          {status || `Runs ${runnable} in your browser. The interviewer sees the output with your answer.`}
        </span>
      </div>
      {(running || result) && (
        <div className="rounded-xl bg-night p-3 text-white" aria-live="polite">
          <p className="mb-1 text-xs font-semibold tracking-wider text-white/60 uppercase">
            Output{stale ? ' (from before your last edit)' : ''}
          </p>
          <pre
            className={`max-h-60 overflow-auto font-mono text-xs leading-relaxed whitespace-pre-wrap ${result?.error ? 'text-red-300' : ''}`}
          >
            {shown || (running ? 'Running…' : '')}
          </pre>
        </div>
      )}
    </div>
  )
}

// The coding round's editor; its contents are sent with each answer.
export default function CodePad({ code, onChange }) {
  const theme = useTheme()
  // Phones get the plain box only: the full editor needs a bigger screen (T-150).
  const small = useSmallScreen()
  const [chosePlain, setPlain] = useState(false)
  const plain = small || chosePlain
  const set = (content) => onChange({ ...code, content: content ?? '' })
  return (
    <section className="card space-y-3 p-4" aria-label="Code editor">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold text-ink">
          <span aria-hidden="true">⌨️ </span>Code editor
        </h2>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-2">
            Language
            <select
              value={code.language}
              onChange={(e) => onChange({ ...code, language: e.target.value })}
              className="rounded-xl border-2 border-field-line bg-surface px-2 py-1"
            >
              {LANGUAGES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {!small && (
            <button type="button" onClick={() => setPlain((p) => !p)} className="btn-link">
              {plain ? 'Use the code editor' : 'Use a plain text box'}
            </button>
          )}
        </div>
      </div>
      {plain ? (
        <PlainBox value={code.content} onChange={set} />
      ) : (
        <div className="overflow-hidden rounded-xl ring-1 ring-slate-200">
          <Suspense fallback={<PlainBox value={code.content} onChange={set} />}>
            <Editor
              height="320px"
              language={code.language}
              value={code.content}
              onChange={set}
              theme={theme === 'dark' ? 'vs-dark' : 'light'}
              loading={<p className="p-4 text-sm text-slate-500">Loading the editor…</p>}
              options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false, tabSize: 4 }}
            />
          </Suspense>
        </div>
      )}
      <RunPanel code={code} onChange={onChange} />
      <p className="text-xs text-slate-500">
        Write your code here and talk it through in your answer. The interviewer sees your latest code each time
        you answer.
      </p>
    </section>
  )
}
