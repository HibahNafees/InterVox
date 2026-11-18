import { useEffect, useState } from 'react'
import { IconTile } from '../components/Art'
import DocumentInput from '../components/DocumentInput'
import { api } from '../lib/api'

const SETTINGS_KEY = 'intervox_lab_settings'
const TABS = [
  ['chat', 'Prep chat'],
  ['debate', 'Debate'],
  ['compare', 'Compare'],
  ['settings', 'Settings'],
]
const AGENT_LABELS = {
  prep: 'Prep coach',
  advocate: 'Hiring manager (for)',
  skeptic: 'Hiring manager (against)',
  judge: 'Judge',
}

function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || null
  } catch {
    return null
  }
}

function saveSettings(settings) {
  try {
    if (settings) localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
    else localStorage.removeItem(SETTINGS_KEY)
  } catch {
    // Storage unavailable: settings last for this visit only.
  }
}

function fromDefaults(defaults) {
  return { model: defaults.model, agents: structuredClone(defaults.agents) }
}

// Saved settings from an older model list fall back to the defaults.
function usable(saved, defaults) {
  if (!saved?.agents || !defaults.models.some((m) => m.id === saved.model)) return fromDefaults(defaults)
  return { model: saved.model, agents: { ...structuredClone(defaults.agents), ...saved.agents } }
}

function maxTemp(defaults, model) {
  return defaults.models.find((m) => m.id === model)?.max_temperature ?? 1
}

function Calls({ n }) {
  return (
    <span className="font-normal opacity-80">
      ({n} call{n === 1 ? '' : 's'})
    </span>
  )
}

function ErrorText({ text }) {
  if (!text) return null
  return (
    <p role="alert" className="text-sm text-red-600">
      {text}
    </p>
  )
}

function TempSlider({ value, max, onChange, label }) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      {label}: <span className="font-mono">{Number(value).toFixed(1)}</span>
      <input
        type="range"
        min="0"
        max={max}
        step="0.1"
        value={Math.min(value, max)}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 block w-full accent-brand-500"
      />
    </label>
  )
}

function PrepChat({ settings, left, cost, onUsage }) {
  const [resumeId, setResumeId] = useState(null)
  const [jdId, setJdId] = useState(null)
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function send(e) {
    e.preventDefault()
    const content = text.trim()
    if (!content) return
    const next = [...messages, { role: 'user', content }]
    setMessages(next)
    setText('')
    setError('')
    setBusy(true)
    try {
      const data = await api('/lab/chat', {
        method: 'POST',
        body: { messages: next, resume_id: resumeId, jd_id: jdId, settings },
      })
      setMessages([...next, { role: 'assistant', content: data.reply }])
      onUsage(data.usage)
    } catch (err) {
      setError(err.message)
      setMessages(messages)
      setText(content)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <DocumentInput kind="resume" value={resumeId} onChange={setResumeId} optional />
        <DocumentInput kind="job_description" value={jdId} onChange={setJdId} optional />
      </div>
      <div className="card space-y-3 p-5">
        {messages.length === 0 ? (
          <p className="text-sm text-slate-500">
            Ask about likely questions, or paste a story and ask for help turning it into a STAR answer. The coach
            only uses facts you give it.
          </p>
        ) : (
          <ol className="space-y-3" aria-label="Conversation">
            {messages.map((m, i) => (
              <li
                key={i}
                className={`whitespace-pre-wrap rounded-2xl p-3 text-sm ${
                  m.role === 'user' ? 'ml-8 bg-brand-100 text-brand-900' : 'mr-8 bg-navy-50 text-slate-800 ring-1 ring-navy-100'
                }`}
              >
                <span className="sr-only">{m.role === 'user' ? 'You: ' : 'Coach: '}</span>
                {m.content}
              </li>
            ))}
          </ol>
        )}
        {busy && (
          <p role="status" className="animate-pulse text-sm text-slate-500">
            Thinking…
          </p>
        )}
        <form onSubmit={send} className="flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor="lab-message">
            Message
          </label>
          <textarea
            id="lab-message"
            rows={2}
            value={text}
            maxLength={4000}
            onChange={(e) => setText(e.target.value)}
            placeholder="What questions will they likely ask me?"
            className="field flex-1 text-sm"
          />
          <button type="submit" className="btn-primary" disabled={busy || !text.trim() || left < cost}>
            Send <Calls n={cost} />
          </button>
        </form>
        <ErrorText text={error} />
      </div>
    </div>
  )
}

function Debate({ settings, left, cost, onUsage }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const data = await api('/lab/debate', { method: 'POST', body: { question, answer, settings } })
      setResult(data)
      onUsage(data.usage)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={run} className="card space-y-3 p-5">
        <label className="block text-sm font-medium text-slate-700">
          Interview question
          <textarea
            rows={2}
            value={question}
            maxLength={4000}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Tell me about a time you led a project."
            className="field mt-1 text-sm"
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Your answer
          <textarea
            rows={5}
            value={answer}
            maxLength={4000}
            onChange={(e) => setAnswer(e.target.value)}
            className="field mt-1 text-sm"
          />
        </label>
        <button
          type="submit"
          className="btn-primary"
          disabled={busy || !question.trim() || !answer.trim() || left < cost}
        >
          {busy ? 'Debating…' : 'Start the debate'} <Calls n={cost} />
        </button>
        <ErrorText text={error} />
      </form>
      {result && (
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <article className="card p-5">
              <p className="eyebrow text-emerald-700">For hiring you</p>
              <p className="mt-2 whitespace-pre-wrap text-sm">{result.for}</p>
            </article>
            <article className="card p-5">
              <p className="eyebrow text-red-700">Against hiring you</p>
              <p className="mt-2 whitespace-pre-wrap text-sm">{result.against}</p>
            </article>
          </div>
          <article className="card space-y-3 p-5">
            <p className="eyebrow">The judge</p>
            <p className="text-3xl font-extrabold">
              {result.verdict.score}
              <span className="text-lg font-semibold text-slate-500"> / 5</span>
            </p>
            <p className="text-xs text-slate-500">
              Practice feedback from an AI, not a hiring decision. Real hiring decisions are made by people.
            </p>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {result.verdict.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            <p className="rounded-2xl bg-brand-100 p-3 text-sm text-brand-900">
              <span className="font-bold">Tip: </span>
              {result.verdict.tip}
            </p>
          </article>
        </div>
      )}
    </div>
  )
}

function Compare({ defaults, left, cost, onUsage }) {
  const [prompt, setPrompt] = useState('')
  const [sides, setSides] = useState([
    { model: defaults.model, temperature: 0 },
    { model: defaults.model, temperature: 1 },
  ])
  const [answers, setAnswers] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function setSide(i, change) {
    setSides((all) =>
      all.map((s, j) => {
        if (j !== i) return s
        const next = { ...s, ...change }
        return { ...next, temperature: Math.min(next.temperature, maxTemp(defaults, next.model)) }
      }),
    )
  }

  async function run(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const data = await api('/lab/compare', { method: 'POST', body: { prompt, sides } })
      setAnswers(data.answers)
      onUsage(data.usage)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={run} className="space-y-4">
      <div className="card space-y-3 p-5">
        <label className="block text-sm font-medium text-slate-700">
          Prompt
          <textarea
            rows={3}
            value={prompt}
            maxLength={4000}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Write a 2-sentence answer to “Why do you want this job?” for a nurse."
            className="field mt-1 text-sm"
          />
        </label>
        <button type="submit" className="btn-primary" disabled={busy || !prompt.trim() || left < cost}>
          {busy ? 'Comparing…' : 'Compare'} <Calls n={cost} />
        </button>
        <ErrorText text={error} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {sides.map((side, i) => (
          <article key={i} className="card space-y-3 p-5">
            <p className="eyebrow">Setting {i === 0 ? 'A' : 'B'}</p>
            <label className="block text-sm font-medium text-slate-700">
              Model
              <select
                value={side.model}
                onChange={(e) => setSide(i, { model: e.target.value })}
                className="field mt-1 text-sm"
              >
                {defaults.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            <TempSlider
              label="Temperature"
              value={side.temperature}
              max={maxTemp(defaults, side.model)}
              onChange={(t) => setSide(i, { temperature: t })}
            />
            {answers && <p className="whitespace-pre-wrap border-t border-line pt-3 text-sm">{answers[i]}</p>}
          </article>
        ))}
      </div>
    </form>
  )
}

function SettingsTab({ defaults, settings, onChange }) {
  const top = maxTemp(defaults, settings.model)

  function setAgent(name, change) {
    onChange({ ...settings, agents: { ...settings.agents, [name]: { ...settings.agents[name], ...change } } })
  }

  return (
    <div className="space-y-4">
      <div className="card space-y-3 p-5">
        <label className="block text-sm font-medium text-slate-700">
          Model for the prep chat and the debate
          <select
            value={settings.model}
            onChange={(e) => {
              const cap = maxTemp(defaults, e.target.value)
              const agents = Object.fromEntries(
                Object.entries(settings.agents).map(([k, a]) => [k, { ...a, temperature: Math.min(a.temperature, cap) }]),
              )
              onChange({ model: e.target.value, agents })
            }}
            className="field mt-1 text-sm"
          >
            {defaults.models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <p className="rounded-2xl bg-navy-50 p-3 text-sm text-navy-800 ring-1 ring-navy-100">
          <span className="font-bold">What is temperature?</span> It controls how much the AI varies its wording. At 0
          it gives nearly the same, most likely answer every time, which suits judging. Near 1 it takes more chances
          and sounds more creative, which suits arguing a side, but it can also wander. The highest setting is {top}.
        </p>
        <button type="button" className="btn-secondary" onClick={() => onChange(null)}>
          Reset to defaults
        </button>
      </div>
      {Object.keys(defaults.agents).map((name) => (
        <div key={name} className="card space-y-3 p-5">
          <p className="eyebrow">{AGENT_LABELS[name] ?? name}</p>
          <label className="block text-sm font-medium text-slate-700">
            System prompt
            <textarea
              rows={4}
              maxLength={4000}
              value={settings.agents[name].system}
              onChange={(e) => setAgent(name, { system: e.target.value })}
              className="field mt-1 text-sm"
            />
          </label>
          <TempSlider
            label="Temperature"
            value={settings.agents[name].temperature}
            max={top}
            onChange={(t) => setAgent(name, { temperature: t })}
          />
        </div>
      ))}
      <p className="text-xs text-slate-500">
        Settings are saved in this browser only. Whatever you write, InterVox always adds its own rules: no invented
        experience, always respectful, practice feedback only.
      </p>
    </div>
  )
}

export default function Lab() {
  const [defaults, setDefaults] = useState(null)
  const [usage, setUsage] = useState(null)
  const [settings, setSettings] = useState(null)
  const [tab, setTab] = useState('chat')
  const [error, setError] = useState('')

  useEffect(() => {
    api('/lab')
      .then((data) => {
        setDefaults(data.defaults)
        setUsage(data.usage)
        setSettings(usable(loadSettings(), data.defaults))
      })
      .catch((err) => setError(err.message))
  }, [])

  function changeSettings(next) {
    saveSettings(next)
    setSettings(next ?? fromDefaults(defaults))
  }

  const left = usage ? usage.cap - usage.used : 0
  const shared = { left, onUsage: setUsage }

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Chat Lab</p>
          <h1 className="mt-1 text-3xl font-extrabold">Prepare, debate, compare</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            Chat with a prep coach, let two hiring managers argue over your answer, or see how the model and
            temperature change a reply.
          </p>
        </div>
        <IconTile tone="navy" className="hidden h-14 w-14 text-2xl sm:grid">
          🧪
        </IconTile>
      </header>

      <ErrorText text={error} />

      {usage && (
        <p role="status" className="chip">
          {usage.used} of {usage.cap} Chat Lab calls used today · a chat costs {defaults.costs.chat}, a compare{' '}
          {defaults.costs.compare}, a debate {defaults.costs.debate}
        </p>
      )}

      {defaults && settings && (
        <>
          <div role="tablist" aria-label="Chat Lab" className="flex flex-wrap gap-1">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                  tab === id ? 'bg-brand-100 text-brand-700' : 'text-slate-600 hover:bg-surface hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {/* Kept mounted so switching tabs doesn't lose a conversation. */}
          <div hidden={tab !== 'chat'}>
            <PrepChat settings={settings} cost={defaults.costs.chat} {...shared} />
          </div>
          <div hidden={tab !== 'debate'}>
            <Debate settings={settings} cost={defaults.costs.debate} {...shared} />
          </div>
          <div hidden={tab !== 'compare'}>
            <Compare defaults={defaults} cost={defaults.costs.compare} {...shared} />
          </div>
          <div hidden={tab !== 'settings'}>
            <SettingsTab defaults={defaults} settings={settings} onChange={changeSettings} />
          </div>
        </>
      )}
    </section>
  )
}
