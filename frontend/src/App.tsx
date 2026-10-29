import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Bench, Caps, CostAgg, Edit, Finding, FindingResult, Result, Session } from './types'
import { BTN_PRIMARY, BTN_SECONDARY, Dot, hue } from './design'
import { ThemeToggle } from './theme'

const TABS = ['Session', 'Benchmark', 'Cost and models'] as const
type Tab = (typeof TABS)[number]
const STAGES = ['Perception', 'Findings', 'Citation', 'Patch', 'Verify'] as const
const STAGE_KEY: Record<string, number> = { perception: 0, findings: 1, citation: 2, patch: 3, verify: 4, done: 5 }

const SEV: Record<string, string> = { critical: 'bg-red/10 text-red-text', high: 'bg-orange/10 text-orange-text', medium: 'bg-ink/5 text-ink', low: 'bg-ink/5 text-muted' }
const ROLE_DOT: Record<string, string> = { perception: 'bg-blue', patch: 'bg-purple', escalation: 'bg-pink' }

const CELL = 'border-b px-1.5 py-1'

const fmt = (n: number, d = 2) => n.toFixed(d)
const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

interface LiveRun { findings: Finding[]; rejected: number; progress: Record<string, { text: string; tone: 'muted' | 'success' | 'destructive' }> }

// What a live pipeline event means for one finding, in plain words.
function progressOf(ev: { stage: string; role?: string; passed?: boolean; reason?: string }): LiveRun['progress'][string] {
  if (ev.stage === 'citation') return { text: 'Finding the W3C guidance…', tone: 'muted' }
  if (ev.stage === 'patch') return { text: `${ev.role === 'escalation' ? 'Nemotron Ultra' : 'Nemotron Super'} wrote a patch · verifying in Chromium…`, tone: 'muted' }
  if (ev.passed) return { text: '✓ Fix verified', tone: 'success' }
  if (ev.role === 'precheck') return { text: '— Not reproduced: the page already passes this check, so nothing to fix', tone: 'muted' }
  return { text: `✕ ${ev.reason || 'Verification failed'}${ev.role === 'escalation' ? '' : ' · trying again'}`, tone: 'destructive' }
}
const money = (c?: CostAgg) => (!c ? '–' : c.cost_known === false ? 'price not set' : `$${c.cost_usd.toFixed(4)}`)

function Badge({ children, dot }: { children: React.ReactNode; dot?: string }) {
  return <span className="inline-flex items-baseline gap-1 rounded-full bg-card px-1.5 text-caption leading-6 text-ink shadow">{dot && <Dot className={dot} />}{children}</span>
}

function Placeholder({ source }: { source?: string }) {
  if (source !== 'oracle_stub') return null
  return (
    <div role="note" className="rounded-lg border border-l-4 border-l-warning bg-card p-2 text-callout shadow">
      <strong className="text-warning-text"><span aria-hidden="true">⚠ </span>Placeholder results.</strong> These come from a reference mapping, not from a model. No Token Factory or Tavily call was made. Run the
      pipeline with live keys (or press “Run live”) to get real findings.
    </div>
  )
}

function Diff({ edits }: { edits: Edit[] }) {
  if (!edits.length) return <p className="text-callout text-muted">No edits proposed.</p>
  return (
    <div className="space-y-1">
      {edits.map((e, i) => (
        <figure key={i} className="overflow-hidden rounded-md border">
          <figcaption className="border-b bg-bg px-1.5 py-1 font-mono text-caption text-muted">{e.file}</figcaption>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-footnote">
            <span className="block bg-red/10 px-1.5 py-1 text-ink"><span aria-label="removed" className="font-semibold text-red-text">− </span>{e.old_str}</span>
            <span className="block bg-green/10 px-1.5 py-1 text-ink"><span aria-label="added" className="font-semibold text-green-text">+ </span>{e.new_str}</span>
          </pre>
        </figure>
      ))}
    </div>
  )
}

function useAudio() {
  const ref = useRef<HTMLAudioElement | null>(null)
  return (path: string | null) => {
    if (!path) return
    ref.current?.pause()
    ref.current = new Audio(`/media/${path}`)
    void ref.current.play()
  }
}

export default function App() {
  const [caps, setCaps] = useState<Caps | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [sid, setSid] = useState('')
  const [tab, setTab] = useState<Tab>('Session')
  const [result, setResult] = useState<Result | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [stage, setStage] = useState(-1)
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [liveCost, setLiveCost] = useState<CostAgg | null>(null)
  const [live, setLive] = useState<LiveRun | null>(null)
  const [startedAt, setStartedAt] = useState(0)
  const [now, setNow] = useState(0)
  const [bench, setBench] = useState<Bench | null>(null)
  const [benchErr, setBenchErr] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)
  const play = useAudio()

  useEffect(() => {
    fetch('/api/capabilities').then(r => r.json()).then(setCaps).catch(() => setError('Could not reach the Heard API.'))
    fetch('/api/sessions').then(r => r.json()).then((s: Session[]) => { setSessions(s); if (s[0]) setSid(s[0].id) })
      .catch(() => setError('Could not load sessions.'))
    fetch('/api/benchmark').then(r => (r.ok ? r.json() : Promise.reject(r))).then(setBench).catch(() => setBenchErr('No benchmark has been generated yet. Run eval/run_eval.py.'))
  }, [])

  const analyze = useCallback(async (id: string, live: boolean) => {
    setRunning(true); setError(''); setStage(0); setResult(null); setSelected(''); setLiveCost(null); setLive(null)
    setStartedAt(Date.now()); setNow(Date.now())
    setStatus(live ? 'Running live analysis…' : 'Loading cached result…')
    try {
      const r = await fetch(`/api/sessions/${id}/analyze?live=${live}`, { method: 'POST' })
      if (!r.ok) {
        let msg = `Request failed (${r.status})`
        try { const j = await r.json(); msg = j.error || j.detail || msg } catch { /* keep default */ }
        throw new Error(msg)
      }
      const reader = r.body!.getReader(); const dec = new TextDecoder(); let buf = ''
      for (;;) {
        const { done, value } = await reader.read(); if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n'); buf = parts.pop() ?? ''
        for (const p of parts) {
          if (!p.startsWith('data: ')) continue
          const ev = JSON.parse(p.slice(6))
          if (ev.stage in STAGE_KEY) setStage(STAGE_KEY[ev.stage])
          if (ev.cost) setLiveCost(ev.cost)
          if (ev.stage === 'findings') setStatus(`Perception found ${ev.supported.length} supported issue(s); ${ev.rejected.length} rejected as unsupported.`)
          if (ev.stage === 'verify') setStatus(`Verification ${ev.passed ? 'passed' : 'failed'} for ${ev.finding}.`)
          if (ev.stage === 'findings' && !ev.cached) setLive({ findings: ev.supported, rejected: ev.rejected.length, progress: {} })
          if (ev.finding && ['citation', 'patch', 'verify'].includes(ev.stage) && !ev.error)
            setLive(l => l && { ...l, progress: { ...l.progress, [ev.finding]: progressOf(ev) } })
          if (ev.stage === 'error') throw new Error(ev.message)
          if (ev.stage === 'done') { setLive(null); setResult(ev.result); setSelected(ev.result.findings[0]?.finding.id ?? ''); setStatus(`Done. ${ev.result.findings.filter((f: FindingResult) => f.fixed).length} of ${ev.result.findings.length} fixes verified.`) }
        }
      }
    } catch (e) { setError((e as Error).message); setStatus('') } finally { setRunning(false) }
  }, [])

  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [running])

  useEffect(() => { const s = sessions.find(x => x.id === sid); if (sid && s?.has_cache) void analyze(sid, false); else { setResult(null) } }, [sid, sessions, analyze])

  const current = useMemo(() => result?.findings.find(f => f.finding.id === selected) ?? null, [result, selected])
  const session = sessions.find(s => s.id === sid)
  const seek = (t: number) => { const v = videoRef.current; if (v) { v.currentTime = t; void v.play() } }
  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    const n = e.key === 'ArrowRight' ? (i + 1) % 3 : e.key === 'ArrowLeft' ? (i + 2) % 3 : e.key === 'Home' ? 0 : e.key === 'End' ? 2 : -1
    if (n >= 0) { e.preventDefault(); setTab(TABS[n]); document.getElementById(`tab-${n}`)?.focus() }
  }
  const cost = running ? liveCost : result?.cost.total

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-1 focus:top-1 focus:z-50 focus:rounded-sm focus:bg-card focus:px-2 focus:py-1">Skip to content</a>
      <header className="mx-auto max-w-page space-y-2 px-2 pb-2 pt-4 sm:px-3">
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <h1 className="text-largeTitle tracking-tight"><a href="/" className="text-ink no-underline hover:underline">Heard</a></h1>
            <p className="text-callout text-ink">Linters read your code. Heard listens to your product.</p>
          </div>
          <ThemeToggle />
        </div>
        <ul className="flex flex-wrap gap-1" aria-label="Configuration">
          <li><Badge dot="bg-teal">Perception mode: {caps?.perception_mode ?? '…'}</Badge></li>
          {caps && Object.entries(caps.models).map(([k, v]) => <li key={k}><Badge dot={ROLE_DOT[k]}>{k}: {v ?? 'not configured'}</Badge></li>)}
          <li><Badge dot="bg-green">Powered by Nebius Token Factory + NVIDIA Nemotron + Tavily</Badge></li>
        </ul>
      </header>

      <main id="main">
        <div className="glass sticky top-0 z-40 border-x-0 border-t-0">
          <div className="mx-auto max-w-page px-2 py-1 sm:px-3">
            <div role="tablist" aria-label="Views" className="inline-flex max-w-full gap-1 overflow-x-auto whitespace-nowrap rounded-md bg-ink/5 p-1">
              {TABS.map((t, i) => (
                <button key={t} id={`tab-${i}`} role="tab" type="button" aria-selected={tab === t} aria-controls={`panel-${i}`} tabIndex={tab === t ? 0 : -1}
                  onClick={() => setTab(t)} onKeyDown={e => onTabKey(e, i)}
                  className={`min-h-tap rounded-sm px-2 py-1.5 text-callout font-semibold ${tab === t ? 'bg-accent-fill text-white shadow' : 'text-ink hover:bg-card'}`}>{t}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="mx-auto max-w-page space-y-3 px-2 py-3 sm:px-3">
        <p role="status" aria-live="polite" className="sr-only">{status}</p>
        {error && <p role="alert" className="rounded-lg border border-l-4 border-l-destructive bg-card p-2 text-callout text-destructive-text shadow"><span aria-hidden="true">✕ </span>{error}</p>}

        <section id="panel-0" role="tabpanel" aria-labelledby="tab-0" hidden={tab !== 'Session'} className="space-y-3">
          <h2 className="text-title">Session analysis</h2>
          <div className="flex flex-wrap items-end gap-2">
            <div className="w-full min-w-0 space-y-1 sm:w-auto">
              <label htmlFor="session" className="block text-subheadline font-semibold">Session</label>
              <select id="session" value={sid} onChange={e => setSid(e.target.value)} className="min-h-tap w-full rounded-sm border bg-card px-1.5 text-callout shadow sm:w-auto">
                {sessions.map(s => <option key={s.id} value={s.id}>{s.site} (buggy) – {s.label}</option>)}
              </select>
            </div>
            <button type="button" disabled={running || !sid || !caps?.live_ready} aria-describedby="live-help" onClick={() => void analyze(sid, true)} className={BTN_PRIMARY}>Run live</button>
            <p id="live-help" className="max-w-md text-footnote text-ink">
              {caps?.live_ready ? `Makes real Token Factory and Tavily calls. Limited to ${caps.rate_limit_per_hour} per hour per visitor.` : 'Live mode is not configured on this server, so cached results are shown.'}
            </p>
          </div>
          <Placeholder source={result?.source} />

          <ol className="flex flex-wrap gap-1 text-footnote" aria-label="Pipeline progress">
            {STAGES.map((s, i) => {
              const state = stage > i || stage === 5 ? 'done' : stage === i ? 'active' : 'pending'
              return <li key={s} className={`rounded-full px-1.5 leading-6 font-semibold shadow ${state === 'done' ? 'bg-card text-success-text' : state === 'active' ? 'bg-accent-fill text-white' : 'bg-card text-muted'}`}>
                <span aria-hidden="true">{state === 'done' ? '✓ ' : state === 'active' ? '… ' : '○ '}</span>{s}<span className="sr-only"> ({state})</span></li>
            })}
          </ol>

          <div className="grid gap-3 lg:grid-cols-3">
            <section aria-labelledby="h-video" className="surface space-y-2 p-2">
              <h3 id="h-video" className="text-title2">Recording</h3>
              <p className="text-footnote text-muted">Simulated screen reader: announcements are built from the browser accessibility tree and synthesized with text-to-speech.</p>
              {session && <video ref={videoRef} key={session.id} src={session.video} controls className="w-full rounded-md bg-black" aria-label={`Screen recording with announcements, ${session.site} site`} />}
              {session && result && (
                <div role="group" aria-label="Findings timeline" className="relative h-8 rounded-md bg-bg">
                  {result.findings.map(f => (
                    <button key={f.finding.id} type="button" onClick={() => { setSelected(f.finding.id); seek(f.finding.t_start) }}
                      aria-label={`Finding ${f.finding.id} at ${fmt(f.finding.t_start, 1)} seconds: ${f.finding.issue_type}`} aria-pressed={selected === f.finding.id}
                      style={{ left: `calc(${Math.min(94, (f.finding.t_start / session.duration) * 100)}% )` }}
                      className={`absolute top-1 h-6 w-3 rounded-sm border-2 shadow ${hue(f.finding.issue_type).dot} ${selected === f.finding.id ? 'border-ink' : 'border-white'}`} />
                  ))}
                </div>
              )}
            </section>

            <section aria-labelledby="h-find" className="surface space-y-2 p-2">
              <h3 id="h-find" className="text-title2">Findings {(result || live) && <span className="text-callout font-normal text-muted">({result?.findings.length ?? live?.findings.length})</span>}</h3>
              {result && <p className="text-callout" data-testid="rejected-count"><strong>{result.rejected_unsupported.length}</strong> rejected as unsupported by the speech log (deterministic evidence check).</p>}
              {!result && !running && <p className="rounded-md border border-dashed p-2 text-callout text-muted">No results yet for this session. Press “Run live” to analyze it.</p>}
              {running && !result && (
                <p className="rounded-md bg-bg p-2 text-callout">
                  <span className="block font-semibold">{live ? `Citing, patching and verifying ${live.findings.length} finding(s) in a real browser` : 'Nemotron Omni is watching the recording and listening to the screen reader'}</span>
                  <span className="block text-footnote text-muted">{clock(Math.max(0, Math.round((now - startedAt) / 1000)))} elapsed{live ? '' : ' · perception usually takes 1–2 minutes'}</span>
                </p>
              )}
              {!result && live && live.rejected > 0 && <p className="text-callout"><strong>{live.rejected}</strong> rejected as unsupported by the speech log (deterministic evidence check).</p>}
              {!result && live && (
                <ol className="space-y-1">
                  {live.findings.map(f => {
                    const pr = live.progress[f.id]
                    return (
                      <li key={f.id} className={`space-y-1 rounded-md border border-l-4 bg-card p-2 ${hue(f.issue_type).bar}`}>
                        <span className="flex flex-wrap items-baseline gap-1">
                          <span className="text-headline">{f.issue_type.replace(/_/g, ' ')}</span>
                          <span className={`rounded-full px-1 text-caption leading-6 font-semibold ${SEV[f.severity] ?? SEV.low}`}>{f.severity}</span>
                          <span className="text-subheadline text-muted">at {fmt(f.t_start, 1)}s</span>
                        </span>
                        <span className="block text-callout"><span className="text-muted">Heard: </span><q>{f.announced_text || 'silence'}</q></span>
                        <span className="block text-callout"><span className="text-muted">Needed: </span>{f.visible_text_or_description}</span>
                        <span className={`block text-subheadline font-semibold ${pr?.tone === 'success' ? 'text-success-text' : pr?.tone === 'destructive' ? 'text-destructive-text' : 'text-muted'}`}>{pr?.text ?? 'Waiting…'}</span>
                      </li>
                    )
                  })}
                </ol>
              )}
              <ol className="space-y-1">
                {result?.findings.map(f => (
                  <li key={f.finding.id}>
                    <button type="button" aria-pressed={selected === f.finding.id} onClick={() => { setSelected(f.finding.id); seek(f.finding.t_start) }}
                      className={`w-full space-y-1 rounded-md border border-l-4 bg-card p-2 ${hue(f.finding.issue_type).bar} ${selected === f.finding.id ? 'shadow ring-2 ring-inset ring-accent' : 'hover:bg-bg'}`}>
                      <span className="flex flex-wrap items-baseline gap-1">
                        <span className="text-headline">{f.finding.issue_type.replace(/_/g, ' ')}</span>
                        <span className={`rounded-full px-1 text-caption leading-6 font-semibold ${SEV[f.finding.severity] ?? SEV.low}`}>{f.finding.severity}</span>
                        <span className="text-subheadline text-muted">at {fmt(f.finding.t_start, 1)}s</span>
                      </span>
                      <span className="block text-callout"><span className="text-muted">Heard: </span><q>{f.finding.announced_text || 'silence'}</q></span>
                      <span className="block text-callout"><span className="text-muted">Needed: </span>{f.finding.visible_text_or_description}</span>
                      <span className={`block text-subheadline font-semibold ${f.fixed ? 'text-success-text' : 'text-destructive-text'}`}>{f.fixed ? '✓ Fix verified' : '✕ Not fixed'}</span>
                    </button>
                  </li>
                ))}
              </ol>
              {result && result.rejected_unsupported.length > 0 && (
                <details className="rounded-md bg-bg p-2 text-callout"><summary className="cursor-pointer font-semibold">Why were {result.rejected_unsupported.length} rejected?</summary>
                  <ul className="mt-1 list-disc space-y-1 pl-3">{result.rejected_unsupported.map((r, i) => <li key={i}>{r.finding.issue_type}: {r.reason}</li>)}</ul></details>
              )}
            </section>

            <section aria-labelledby="h-fix" className="surface space-y-2 p-2">
              <h3 id="h-fix" className="text-title2">Patch and verification</h3>
              {!current && <p className="rounded-md border border-dashed p-2 text-callout text-muted">Select a finding to see its patch.</p>}
              {current && (
                <>
                  <div className="space-y-1 text-callout">
                    <p className="flex items-baseline gap-1 text-headline"><Dot className={hue(current.finding.issue_type).dot} />WCAG {current.finding.wcag_guess}</p>
                    {current.citations.length > 0 && <ul className="list-disc space-y-1 pl-3">{current.citations.map(c => <li key={c.url}><a href={c.url} target="_blank" rel="noreferrer">{c.title || c.url}<span className="sr-only"> (opens in a new tab)</span></a></li>)}</ul>}
                  </div>
                  <Diff edits={current.final?.edits ?? []} />
                  {current.final?.rationale && <p className="text-callout">{current.final.rationale}</p>}
                  <div className={`space-y-1 rounded-md p-2 text-callout ${current.fixed ? 'bg-success/10' : 'bg-destructive/10'}`}>
                    <p className={`text-headline ${current.fixed ? 'text-success-text' : 'text-destructive-text'}`}>{current.fixed ? '✓ Verified' : '✕ Verification failed'}{current.model_used ? ` · fixed by ${current.model_used}` : ''}{current.attempts.length > 1 ? ` · ${current.attempts.length} attempts` : ''}</p>
                    {current.final?.reason && <p>{current.final.reason}</p>}
                    <ul className="list-disc space-y-1 pl-3">{current.final?.verification?.checks.map((c, i) => <li key={i}>{c}</li>)}</ul>
                    <p className="text-footnote text-ink">Verification is a deterministic accessibility-tree proxy for screen-reader output, not a live screen reader.</p>
                  </div>
                  <div role="group" aria-label="Hear it" className="space-y-1 rounded-md bg-bg p-2">
                    <p className="text-headline">Hear it</p>
                    <div className="flex flex-wrap gap-1">
                      <button type="button" onClick={() => play(current.before_audio)} disabled={!current.before_audio} className={BTN_SECONDARY}>▶ Before</button>
                      <button type="button" onClick={() => play(current.after_audio)} disabled={!current.after_audio} className={BTN_PRIMARY}>▶ After {current.fixed ? '✓' : '✕'}</button>
                    </div>
                    <p className="text-footnote text-muted">Before: “{current.finding.announced_text || 'silence'}” · After: “{current.final?.verification?.after_announcement || 'n/a'}”</p>
                  </div>
                </>
              )}
            </section>
          </div>
        </section>

        <section id="panel-1" role="tabpanel" aria-labelledby="tab-1" hidden={tab !== 'Benchmark'} className="space-y-3">
          <h2 className="text-title">axe-core alone vs Heard</h2>
          {benchErr && <p className="text-callout">{benchErr}</p>}
          {bench && (
            <>
              <Placeholder source={bench.source.includes('oracle_stub') ? 'oracle_stub' : ''} />
              <dl className="grid max-w-3xl grid-cols-2 gap-2 sm:grid-cols-4">
                {([['axe-core detected', `${bench.axe_detected}/${bench.total_bugs}`, 'text-orange-text'], ['Heard detected', `${bench.heard_detected}/${bench.total_bugs}`, 'text-accent-text'], ['Fixes verified', `${bench.fixes_verified}/${bench.heard_detected}`, 'text-success-text'], ['Rejected unsupported', String(bench.rejected_unsupported), 'text-purple-text']] as const).map(([k, v, c]) => (
                  <div key={k} className="glass space-y-1 rounded-lg p-2"><dt className="text-subheadline text-ink">{k}</dt><dd className={`text-title ${c}`}>{v}</dd></div>))}
              </dl>
              <div className="surface overflow-x-auto"><table className="w-full min-w-table border-collapse text-callout">
                <caption className="sr-only">Per-bug detection results</caption>
                <thead><tr className="bg-bg">{['Bug', 'Site', 'Category', 'axe-core', 'Heard', 'Fix verified'].map(h => <th key={h} scope="col" className={`${CELL} font-semibold`}>{h}</th>)}</tr></thead>
                <tbody>{bench.bugs.map(b => <tr key={b.id}>
                  <th scope="row" className={`${CELL} font-semibold`}>{b.id}</th><td className={CELL}>{b.site}</td>
                  <td className={CELL}><span className="inline-flex items-baseline gap-1"><Dot className={hue(b.category).dot} />{b.category.replace(/_/g, ' ')}</span></td>
                  {[b.axe_detected, b.heard_detected, b.fix_verified].map((v, i) => <td key={i} className={`${CELL} ${v ? 'font-semibold text-success-text' : 'text-muted'}`}>{v ? '✓ yes' : '✕ no'}</td>)}</tr>)}</tbody></table></div>
              <p className="max-w-3xl text-footnote text-ink">{bench.matching_rule}</p>
            </>
          )}
        </section>

        <section id="panel-2" role="tabpanel" aria-labelledby="tab-2" hidden={tab !== 'Cost and models'} className="space-y-3">
          <h2 className="text-title">Cost and models</h2>
          <p aria-live="polite" className="glass rounded-lg p-2 text-callout" data-testid="live-cost">
            {cost ? <>Calls: <strong>{cost.calls}</strong> · tokens in/out: <strong>{cost.input_tokens}/{cost.output_tokens}</strong> · latency: <strong>{fmt(cost.latency_s, 1)}s</strong> · est. cost: <strong>{money(cost)}</strong></> : 'No model calls in this view yet.'}
          </p>
          {result && (['by_stage', 'by_model'] as const).map(k => (
            <div key={k} className="surface overflow-x-auto p-2"><table className="w-full min-w-table border-collapse text-callout">
              <caption className="pb-1 text-headline">{k === 'by_stage' ? 'By stage' : 'By model'}</caption>
              <thead><tr className="bg-bg">{[k === 'by_stage' ? 'Stage' : 'Model', 'Calls', 'Input tokens', 'Output tokens', 'Latency', 'Est. cost'].map(h => <th key={h} scope="col" className={`${CELL} font-semibold`}>{h}</th>)}</tr></thead>
              <tbody>{Object.entries(result.cost[k]).map(([name, v]) => <tr key={name}><th scope="row" className={`${CELL} font-mono text-footnote`}>{name}</th>
                <td className={CELL}>{v.calls}</td><td className={CELL}>{v.input_tokens}</td><td className={CELL}>{v.output_tokens}</td><td className={CELL}>{fmt(v.latency_s, 1)}s</td><td className={CELL}>{money(v)}</td></tr>)}</tbody></table></div>))}
          {result && Object.keys(result.cost.by_stage).length === 0 && <p className="text-callout text-ink">This result was produced without model calls (placeholder), so there is nothing to price.</p>}
        </section>
        </div>
      </main>
      <footer className="mx-auto max-w-page px-2 pb-4 text-footnote text-ink sm:px-3"><a href="/">About Heard</a> · MIT licensed · Sessions are simulated screen-reader sessions · Verification is an accessibility-tree proxy.</footer>
    </div>
  )
}
