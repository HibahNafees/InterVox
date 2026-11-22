import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CompanyResearch from '../components/CompanyResearch'
import DocumentInput from '../components/DocumentInput'
import GapAnalysis from '../components/GapAnalysis'
import QuestionsCoach from '../components/QuestionsCoach'
import { api } from '../lib/api'
import { answerModePref, canRecord, setAnswerModePref } from '../lib/recording'
import { HANDS_ON, useSmallScreen } from '../lib/useSmallScreen'
import { usesFireVoice, voicePref } from '../lib/voice'

const DURATIONS = [10, 30, 45, 60]
const NEGOTIATION_DURATIONS = [5, 10, 15, 20]
const FORMATS = [
  ['standard', 'One interviewer'],
  ['panel', '👥 Panel'],
  ['negotiation', '💰 Salary negotiation'],
]
const FORMAT_BLURBS = {
  standard: 'A one-to-one interview.',
  panel: 'Two or three interviewers (hiring manager, a future colleague and HR) take turns, each with their own voice.',
  negotiation:
    'A recruiter calls with an offer below what you want. Practice anchoring, justifying your number and staying calm. Scored on all three.',
}

// Role detection for the chosen job description, and the interview types that fit.
function useJobAnalysis(jdId) {
  const [state, setState] = useState({ status: 'idle' })
  useEffect(() => {
    if (!jdId) {
      setState({ status: 'idle' })
      return
    }
    let live = true
    setState({ status: 'loading' })
    api(`/documents/${jdId}/analysis`, { method: 'POST' })
      .then((data) => live && setState({ status: 'ready', ...data }))
      .catch((err) => live && setState({ status: 'error', error: err.message }))
    return () => {
      live = false
    }
  }, [jdId])
  return state
}

function Choice({ name, options, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={name}>
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={value === key}
          onClick={() => onChange(key)}
          className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
            value === key
              ? 'border-transparent bg-gradient-to-r from-brand-600 to-accent-500 text-white shadow-md shadow-brand-500/25'
              : 'border-slate-200 bg-surface text-slate-700 hover:border-brand-300 hover:text-brand-700'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

// How many coding problems or design questions. `presets` are the quick
// choices ([value, label]); Custom picks any count from 1 to 10.
function HandsOnCount({ label, name, presets, value, onChange, autoNote }) {
  const custom = value !== 'auto' && !presets.some(([v]) => v === value)
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-ink">{label}</p>
      <Choice
        name={name}
        options={[['auto', 'Let the plan decide'], ...presets, ['custom', 'Custom']]}
        value={custom ? 'custom' : value}
        onChange={(v) => onChange(v === 'custom' ? (custom ? value : 4) : v)}
      />
      {custom && (
        <label className="flex items-center gap-3 text-sm">
          <input
            type="range"
            min={1}
            max={10}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            aria-label={`${name}: how many`}
            className="accent-brand-600"
          />
          <span>{value}</span>
        </label>
      )}
      {value === 'auto' && autoNote && <p className="text-xs text-slate-500">{autoNote}</p>}
    </div>
  )
}

export default function Setup() {
  const navigate = useNavigate()
  const small = useSmallScreen()
  const [resumeId, setResumeId] = useState(null)
  const [jdId, setJdId] = useState(null)
  const [duration, setDuration] = useState(10)
  const [custom, setCustom] = useState(false)
  const [difficulty, setDifficulty] = useState('mid')
  const [persona, setPersona] = useState('neutral')
  const [pressure, setPressure] = useState(0)
  const [focus, setFocus] = useState('mixed')
  const [startNow, setStartNow] = useState(false)
  const [answerMode, setAnswerMode] = useState(answerModePref)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [format, setFormat] = useState('standard')
  const [codingProblems, setCodingProblems] = useState('auto') // 'auto' or a count, 0–10
  const [design, setDesign] = useState('auto') // 'auto' or a count, 0–10
  const [terms, setTerms] = useState({ offer: '', target: '', company: '' })
  const [company, setCompany] = useState(null)
  const [whyUs, setWhyUs] = useState(true)
  const job = useJobAnalysis(jdId)
  const [fits, setFits] = useState([])

  useEffect(() => {
    if (!jdId) {
      setFits([])
      return
    }
    let live = true
    api(`/stories/suggest?jd_id=${jdId}`)
      .then((data) => live && setFits(data.stories ?? []))
      .catch(() => live && setFits([]))
    return () => {
      live = false
    }
  }, [jdId])
  const allModules = job.status === 'ready' ? job.modules : []
  // Phones get no coding or whiteboard rounds: both need a bigger screen (T-150).
  const offered = small ? allModules.filter((m) => !HANDS_ON.includes(m.name)) : allModules
  const handsOnHidden = small && allModules.some((m) => HANDS_ON.includes(m.name))
  // A type that fit the previous job description may not fit this one.
  const chosen = focus === 'mixed' || offered.some((m) => m.name === focus) ? focus : 'mixed'
  const negotiating = format === 'negotiation'
  const termsReady = !negotiating || (terms.offer.trim() && terms.target.trim())
  // A negotiation is a short call; the plan is fixed, so it starts right away.
  const length = negotiating ? Math.min(duration, 20) : duration
  const startNowFor = startNow || negotiating

  // Hands-on rounds the candidate can ask for (T-65), when the job fits them, with
  // any interview type (T-95). Outside a mixed loop, "Let the plan decide" adds none.
  const offersCoding = offered.some((m) => m.name === 'coding')
  const offersDesign = offered.some((m) => m.name === 'system_design')
  const planAddsCoding = ['mixed', 'coding'].includes(chosen)
  const planAddsDesign = ['mixed', 'system_design'].includes(chosen)
  const typeLabel = offered.find((m) => m.name === chosen)?.label
  // Same limits as the planner (planning.fit_counts / fit_hands_on). A count the
  // candidate picks (1–10) gets at least 4 minutes per coding problem and 5 per
  // design question; a round the plan decides needs 8 or 10. A mixed interview
  // keeps 2 minutes for everything else.
  const spare = chosen === 'coding' ? length : length - 2
  const hidden = (name) => small && allModules.some((m) => m.name === name)
  const codingCount = hidden('coding') ? 0 : offersCoding && codingProblems !== 'auto' ? codingProblems : null
  const designCount = hidden('system_design') ? 0 : offersDesign && design !== 'auto' ? design : null
  const chosenMinutes = (codingCount ?? 0) * 4 + (designCount ?? 0) * 5
  const countsFit = chosenMinutes <= spare || (chosen === 'coding' && codingCount === 1)
  const autoCodingFits = chosen === 'coding' || spare - (designCount ?? 0) * 5 >= 8
  const autoCodingMinutes =
    codingProblems === 'auto' && offersCoding && planAddsCoding && autoCodingFits && chosen !== 'system_design' ? 8 : 0
  const autoDesignFits = chosen === 'system_design' || spare - (codingCount ?? 0) * 4 - autoCodingMinutes >= 10
  const onlyType = typeLabel ? `Only ${typeLabel} questions unless you pick a number.` : null

  function choosePressure(level) {
    setPressure(level)
  }

  function chooseFormat(f) {
    setFormat(f)
    // Pressure works one-to-one or with a panel; a negotiation has none (T-132).
    if (f === 'negotiation') setPressure(0)
    if (f === 'negotiation' && duration > 20) {
      setDuration(10)
      setCustom(false)
    }
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const { session } = await api('/sessions', {
        method: 'POST',
        body: {
          resume_id: resumeId,
          jd_id: jdId,
          duration_min: length,
          difficulty,
          persona,
          focus: chosen,
          pressure_level: pressure,
          format,
          ...(negotiating ? { negotiation: terms } : {}),
          ...(!negotiating && codingCount !== null ? { coding_problems: codingCount } : {}),
          ...(!negotiating && designCount !== null ? { system_design: designCount } : {}),
          ...(company && whyUs && !negotiating ? { company_research_id: company.id } : {}),
        },
      })
      setAnswerModePref(answerMode)
      if (!startNowFor) {
        navigate(`/interview/${session.id}`)
        return
      }
      // Skip the plan screen: start now and greet on the interview page.
      try {
        const fire = usesFireVoice(session.voice) && voicePref()
        const data = await api(`/sessions/${session.id}/start`, {
          method: 'POST',
          ...(fire ? { body: { speak: true } } : {}),
        })
        navigate(`/interview/${session.id}`, {
          state: {
            greeting: { segments: data.session.transcript[0]?.segments, clips: data.speech, capped: data.voice_capped },
          },
        })
      } catch {
        // e.g. a daily cap: the plan screen shows the reason when they press Start.
        navigate(`/interview/${session.id}`)
      }
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <header>
        <p className="eyebrow">{startNowFor ? 'Set up your interview' : 'Step 1 of 2'}</p>
        <h1 className="mt-1 text-3xl font-extrabold text-slate-900">New interview</h1>
        <p className="mt-2 text-slate-600">
          Add your résumé and the job you're going for, then choose how you want to practice.
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-2">
        <DocumentInput kind="resume" value={resumeId} onChange={setResumeId} />
        <DocumentInput kind="job_description" value={jdId} onChange={setJdId} />
      </div>

      {job.status === 'loading' && (
        <p role="status" className="animate-pulse text-sm text-slate-500">
          Reading the job description…
        </p>
      )}
      {job.status === 'error' && (
        <p role="alert" className="text-sm text-red-600">
          {job.error}
        </p>
      )}
      {resumeId && jdId && job.status === 'ready' && <GapAnalysis resumeId={resumeId} jdId={jdId} />}
      {jdId && job.status === 'ready' && <QuestionsCoach jdId={jdId} />}
      {jdId && job.status === 'ready' && !negotiating && (
        <CompanyResearch
          role={job.analysis.role_title}
          research={company}
          onChange={setCompany}
          include={whyUs}
          onIncludeChange={setWhyUs}
        />
      )}

      {fits.length > 0 && (
        <section className="card space-y-3 p-5">
          <h2 className="font-semibold text-slate-900">
            <span aria-hidden="true">📚 </span>Stories that fit this job
          </h2>
          <p className="text-sm text-slate-500">From your story bank. Have them ready to tell.</p>
          <ul className="space-y-2">
            {fits.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-ink">{s.title}</span>
                {s.fits.map((f) => (
                  <span key={f} className="chip bg-emerald-50 text-emerald-700">
                    {f}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card space-y-3 p-5">
        <h2 className="font-semibold text-slate-900">Format</h2>
        <Choice name="Format" options={FORMATS} value={format} onChange={chooseFormat} />
        <p className="text-sm text-slate-500">{FORMAT_BLURBS[format]}</p>
        {negotiating && (
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              ['offer', 'The offer', 'e.g. $80,000 base'],
              ['target', "What you're aiming for", 'e.g. $92,000'],
              ['company', 'Company (optional)', 'e.g. Acme'],
            ].map(([key, label, hint]) => (
              <label key={key} className="space-y-1 text-sm font-medium text-ink">
                <span>{label}</span>
                <input
                  value={terms[key]}
                  maxLength={120}
                  onChange={(e) => setTerms((t) => ({ ...t, [key]: e.target.value }))}
                  placeholder={hint}
                  className="field"
                />
              </label>
            ))}
          </div>
        )}
      </section>

      {job.status === 'ready' && !negotiating && (
        <section className="card space-y-3 p-5">
          <h2 className="font-semibold text-slate-900">Interview type</h2>
          <p className="text-sm text-slate-600">
            {job.analysis.role_title} · {job.analysis.field}
            {job.analysis.competencies.length > 0 && ` · ${job.analysis.competencies.map((c) => c.name).join(', ')}`}
          </p>
          <Choice
            name="Interview type"
            options={[['mixed', 'Full mixed loop'], ...offered.map((m) => [m.name, m.label])]}
            value={chosen}
            onChange={setFocus}
          />
          <p className="text-sm text-slate-500">
            {chosen === 'mixed'
              ? 'A realistic loop mixing the formats that fit this job.'
              : offered.find((m) => m.name === chosen)?.blurb}
          </p>
          {handsOnHidden && (
            <p className="text-sm text-slate-500">
              Coding and whiteboard rounds need a bigger screen; open InterVox on a computer for them.
            </p>
          )}
        </section>
      )}

      {job.status === 'ready' && !negotiating && (offersCoding || offersDesign) && (
        <section className="card space-y-4 p-5">
          <h2 className="font-semibold text-slate-900">
            <span aria-hidden="true">⌨️ </span>Hands-on rounds
          </h2>
          {offersCoding && (
            <HandsOnCount
              label="Coding problems (in a code editor)"
              name="Coding problems"
              presets={[
                [0, 'None'],
                [1, '1'],
                [2, '2'],
                [3, '3'],
              ]}
              value={codingProblems}
              onChange={setCodingProblems}
              autoNote={
                !planAddsCoding
                  ? onlyType
                  : autoCodingFits
                    ? null
                    : 'The plan would leave coding out: a problem needs about 8 minutes.'
              }
            />
          )}
          {offersDesign && (
            <HandsOnCount
              label="System design question (on a whiteboard)"
              name="System design"
              presets={[
                [1, 'Include one'],
                [0, 'Skip it'],
              ]}
              value={design}
              onChange={setDesign}
              autoNote={
                !planAddsDesign
                  ? onlyType
                  : autoDesignFits
                    ? null
                    : 'The plan would leave design out: a question needs about 10 minutes.'
              }
            />
          )}
          {!countsFit && (
            <p role="alert" className="text-sm text-red-700">
              {[
                codingCount ? `${codingCount} coding problem${codingCount === 1 ? '' : 's'} (4+ min each)` : null,
                designCount ? `${designCount} design question${designCount === 1 ? '' : 's'} (5+ min each)` : null,
              ]
                .filter(Boolean)
                .join(' and ')}{' '}
              need at least {chosenMinutes} minutes, and this interview has {spare} for them. Choose a longer interview
              or fewer questions.
            </p>
          )}
        </section>
      )}

      <div className="card grid gap-6 p-5 md:grid-cols-3">
        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Length</h2>
          <Choice
            name="Length"
            options={[
              ...(negotiating ? NEGOTIATION_DURATIONS : DURATIONS).map((d) => [d, `${d} min`]),
              ['custom', 'Custom'],
            ]}
            value={custom ? 'custom' : length}
            onChange={(v) => {
              setCustom(v === 'custom')
              if (v !== 'custom') setDuration(v)
            }}
          />
          {custom && (
            <label className="flex items-center gap-3 text-sm">
              <input
                type="range"
                min={5}
                max={negotiating ? 20 : 60}
                value={length}
                onChange={(e) => setDuration(Number(e.target.value))}
                aria-label="Custom length in minutes"
                className="accent-brand-600"
              />
              <span>{length} minutes</span>
            </label>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Difficulty</h2>
          <Choice
            name="Difficulty"
            options={[
              ['entry', 'Entry'],
              ['mid', 'Mid'],
              ['senior', 'Senior'],
            ]}
            value={difficulty}
            onChange={setDifficulty}
          />
        </section>

        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">{negotiating ? 'Recruiter' : 'Interviewer'}</h2>
          <Choice
            name="Interviewer"
            options={[
              ['friendly', 'Friendly'],
              ['neutral', 'Neutral'],
              ['tough', 'Tough'],
            ]}
            value={persona}
            onChange={setPersona}
          />
        </section>
      </div>

      {!negotiating && (
        <section className="card space-y-3 p-5">
          <h2 className="font-semibold text-slate-900">
            <span aria-hidden="true">🔥 </span>Pressure
          </h2>
          <Choice
            name="Pressure"
            options={[
              [0, 'Off'],
              [1, '1 · Skeptical'],
              [2, '2 · Pushback'],
              [3, '3 · 60 s answers'],
              [4, '4 · 45 s + curveballs'],
              [5, '5 · 30 s, demanding'],
            ]}
            value={pressure}
            onChange={choosePressure}
          />
          <p className="text-sm text-slate-500">
            {pressure === 0
                ? 'A normal interview.'
                : 'Practice staying composed: the interviewer gets tougher between answers (always respectful), and higher levels add answer time limits and curveballs. Scoring stays the same, and you can ease off or stop at any time. Your report shows a composure score.'}
          </p>
        </section>
      )}

      <div className="card grid gap-6 p-5 md:grid-cols-2">
        {!negotiating && (
          <section className="space-y-3">
            <h2 className="font-semibold text-slate-900">Before you start</h2>
            <Choice
              name="Questions"
              options={[
                ['review', 'Review the questions first'],
                ['start', 'Start right away'],
              ]}
              value={startNow ? 'start' : 'review'}
              onChange={(v) => setStartNow(v === 'start')}
            />
            <p className="text-sm text-slate-500">
              {startNow
                ? 'The questions stay a surprise, like a real interview.'
                : 'See the plan, edit any question or the minutes, then start.'}
            </p>
          </section>
        )}
        <section className="space-y-3">
          <h2 className="font-semibold text-slate-900">Answer by</h2>
          <Choice
            name="Answer by"
            options={[...(canRecord() ? [['voice', '🎙️ Speaking']] : []), ['text', '⌨️ Typing']]}
            value={answerMode}
            onChange={setAnswerMode}
          />
          <p className="text-sm text-slate-500">
            {answerMode === 'voice'
              ? 'Recording starts by itself when the interviewer finishes speaking.'
              : 'Type each answer. You can switch to speaking any time.'}
          </p>
        </section>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy || !resumeId || !jdId || job.status !== 'ready' || !termsReady || (!negotiating && !countsFit)}
        className="btn-primary"
      >
        {busy
          ? startNowFor
            ? 'Getting your interview ready…'
            : 'Building your interview plan…'
          : negotiating
            ? 'Start the call'
            : startNow
              ? 'Start my interview'
              : 'Build my interview plan'}
      </button>
      {busy && (
        <p className="text-sm text-slate-500">Reading the job description and your résumé; this takes a few seconds.</p>
      )}
    </form>
  )
}
