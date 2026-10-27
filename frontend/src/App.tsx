import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Bench, Caps, CostAgg, Edit, FindingResult, Result, Session } from './types'

const TABS = ['Session', 'Benchmark', 'Cost and models'] as const
type Tab = (typeof TABS)[number]
const STAGES = ['Perception', 'Findings', 'Citation', 'Patch', 'Verify'] as const
const STAGE_KEY: Record<string, number> = { perception: 0, findings: 1, citation: 2, patch: 3, verify: 4, done: 5 }
const SEV: Record<string, string> = { critical: 'bg-red-100 text-red-900', high: 'bg-orange-100 text-orange-900', medium: 'bg-amber-100 text-amber-900', low: 'bg-slate-200 text-slate-900' }

const fmt = (n: number, d = 2) => n.toFixed(d)
const money = (c?: CostAgg) => (!c ? '–' : c.cost_known === false ? 'price not set' : `$${c.cost_usd.toFixed(4)}`)

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="inline-block rounded-full border border-accent/30 bg-accent-soft px-3 py-1 text-xs font-medium text-accent-dark">{children}</span>
}

function Placeholder({ source }: { source?: string }) {
  if (source !== 'oracle_stub') return null
  return (
    <div role="note" className="rounded-lg border-2 border-amber-500 bg-amber-50 p-3 text-sm text-amber-950">
      <strong>Placeholder results.</strong> These come from a reference mapping, not from a model. No Token Factory or Tavily call was made. Run the
      pipeline with live keys (or press “Run live”) to get real findings.
    </div>
  )
}

function Diff({ edits }: { edits: Edit[] }) {
  if (!edits.length) return <p className="text-sm text-slate-600">No edits proposed.</p>
  return (
    <div className="space-y-3">
      {edits.map((e, i) => (
        <figure key={i} className="overflow-hidden rounded-lg border border-slate-300">
          <figcaption className="border-b border-slate-300 bg-slate-100 px-3 py-1 font-mono text-xs text-slate-700">{e.file}</figcaption>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words p-3 font-mono text-xs leading-relaxed">
            <span className="block bg-red-50 text-red-950"><span aria-label="removed">− </span>{e.old_str}</span>
            <span className="block bg-green-50 text-green-950"><span aria-label="added">+ </span>{e.new_str}</span>
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
    setRunning(true); setError(''); setStage(0); setResult(null); setSelected(''); setLiveCost(null)
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
          if (ev.stage === 'error') throw new Error(ev.message)
          if (ev.stage === 'done') { setResult(ev.result); setSelected(ev.result.findings[0]?.finding.id ?? ''); setStatus(`Done. ${ev.result.findings.filter((f: FindingResult) => f.fixed).length} of ${ev.result.findings.length} fixes verified.`) }
        }
      }
    } catch (e) { setError((e as Error).message); setStatus('') } finally { setRunning(false) }
  }, [])

  useEffect(() => { const s = sessions.find(x => x.id === sid); if (sid && s?.has_cache) void analyze(sid, false); else { setResult(null) } }, [sid, sessions, analyze])

  const current = useMemo(() => result?.findings.find(f => f.finding.id === selected) ?? null, [result, selected])
  const session = sessions.find(s => s.id === sid)
  const seek = (t: number) => { const v = videoRef.current; if (v) { v.currentTime = t; void v.play() } }
  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    const n = e.key === 'ArrowRight' ? (i + 1) % 3 : e.key === 'ArrowLeft' ? (i + 2) % 3 : e.key === 'Home' ? 0 : e.key === 'End' ? 2 : -1
    if (n >= 0) { e.preventDefault(); setTab(TABS[n]); document.getElementById(`tab-${n}`)?.focus() }
  }

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">Skip to content</a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-[1400px] px-4 py-5 sm:px-6">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <h1 className="text-3xl font-bold tracking-tight text-accent-dark">Heard</h1>
            <p className="text-base text-slate-700">Linters read your code. Heard listens to your product.</p>
          </div>
          <ul className="mt-3 flex flex-wrap gap-2" aria-label="Configuration">
            <li><Badge>Perception mode: {caps?.perception_mode ?? '…'}</Badge></li>
            {caps && Object.entries(caps.models).map(([k, v]) => <li key={k}><Badge>{k}: {v ?? 'not configured'}</Badge></li>)}
            <li><Badge>Powered by Nebius Token Factory + NVIDIA Nemotron + Tavily</Badge></li>
          </ul>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-[1400px] px-4 py-5 sm:px-6">
        <div role="tablist" aria-label="Views" className="mb-5 flex gap-1 border-b border-slate-300">
          {TABS.map((t, i) => (
            <button key={t} id={`tab-${i}`} role="tab" type="button" aria-selected={tab === t} aria-controls={`panel-${i}`} tabIndex={tab === t ? 0 : -1}
              onClick={() => setTab(t)} onKeyDown={e => onTabKey(e, i)}
              className={`-mb-px rounded-t-md border border-b-0 px-4 py-2 text-sm font-semibold ${tab === t ? 'border-slate-300 bg-white text-accent-dark' : 'border-transparent text-slate-700 hover:bg-slate-100'}`}>{t}</button>
          ))}
        </div>

        <p role="status" aria-live="polite" className="sr-only">{status}</p>
        {error && <p role="alert" className="mb-4 rounded-lg border border-red-400 bg-red-50 p-3 text-sm text-red-950">{error}</p>}

        <section id="panel-0" role="tabpanel" aria-labelledby="tab-0" hidden={tab !== 'Session'}>
          <div className="mb-4 flex flex-wrap items-end gap-4">
            <div>
              <label htmlFor="session" className="block text-sm font-semibold">Session</label>
              <select id="session" value={sid} onChange={e => setSid(e.target.value)} className="mt-1 rounded-md border border-slate-400 bg-white px-3 py-2 text-sm">
                {sessions.map(s => <option key={s.id} value={s.id}>{s.site} (buggy) – {s.label}</option>)}
              </select>
            </div>
            <button type="button" disabled={running || !sid || !caps?.live_ready} aria-describedby="live-help" onClick={() => void analyze(sid, true)}
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:bg-slate-400 disabled:text-slate-950">Run live</button>
            <p id="live-help" className="max-w-md text-xs text-slate-700">
              {caps?.live_ready ? `Makes real Token Factory and Tavily calls. Limited to ${caps.rate_limit_per_hour} per hour per visitor.` : 'Live mode is not configured on this server, so cached results are shown.'}
            </p>
          </div>
          <Placeholder source={result?.source} />

          <ol className="my-4 flex flex-wrap gap-2 text-xs" aria-label="Pipeline progress">
            {STAGES.map((s, i) => {
              const state = stage > i || stage === 5 ? 'done' : stage === i ? 'active' : 'pending'
              return <li key={s} className={`rounded-full border px-3 py-1 font-medium ${state === 'done' ? 'border-green-700 bg-green-50 text-green-950' : state === 'active' ? 'border-accent bg-accent-soft text-accent-dark' : 'border-slate-300 bg-white text-slate-700'}`}>
                <span aria-hidden="true">{state === 'done' ? '✓ ' : state === 'active' ? '… ' : '○ '}</span>{s}<span className="sr-only"> ({state})</span></li>
            })}
          </ol>

          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.1fr)]">
            <section aria-labelledby="h-video" className="space-y-3">
              <h2 id="h-video" className="text-lg font-semibold">Recording</h2>
              <p className="text-xs text-slate-700">Simulated screen reader: announcements are built from the browser accessibility tree and synthesized with text-to-speech.</p>
              {session && <video ref={videoRef} key={session.id} src={session.video} controls className="w-full rounded-lg border border-slate-300 bg-black" aria-label={`Screen recording with announcements, ${session.site} site`} />}
              {session && result && (
                <div role="group" aria-label="Findings timeline" className="relative h-10 rounded-md border border-slate-300 bg-white">
                  {result.findings.map(f => (
                    <button key={f.finding.id} type="button" onClick={() => { setSelected(f.finding.id); seek(f.finding.t_start) }}
                      aria-label={`Finding ${f.finding.id} at ${fmt(f.finding.t_start, 1)} seconds: ${f.finding.issue_type}`} aria-pressed={selected === f.finding.id}
                      style={{ left: `calc(${Math.min(97, (f.finding.t_start / session.duration) * 100)}% )` }}
                      className={`absolute top-1 h-8 w-3 rounded-sm border ${selected === f.finding.id ? 'border-accent-dark bg-accent' : 'border-amber-800 bg-amber-400'}`} />
                  ))}
                </div>
              )}
            </section>

            <section aria-labelledby="h-find" className="space-y-3">
              <h2 id="h-find" className="text-lg font-semibold">Findings {result && <span className="text-sm font-normal text-slate-700">({result.findings.length})</span>}</h2>
              {result && <p className="text-sm" data-testid="rejected-count"><strong>{result.rejected_unsupported.length}</strong> rejected as unsupported by the speech log (deterministic evidence check).</p>}
              {!result && !running && <p className="rounded-lg border border-dashed border-slate-400 p-4 text-sm text-slate-700">No results yet for this session. Press “Run live” to analyze it.</p>}
              {running && !result && <p className="rounded-lg border border-slate-300 bg-white p-4 text-sm">Working…</p>}
              <ol className="space-y-2">
                {result?.findings.map(f => (
                  <li key={f.finding.id}>
                    <button type="button" aria-pressed={selected === f.finding.id} onClick={() => { setSelected(f.finding.id); seek(f.finding.t_start) }}
                      className={`w-full rounded-lg border p-3 text-left ${selected === f.finding.id ? 'border-accent bg-accent-soft' : 'border-slate-300 bg-white hover:border-slate-500'}`}>
                      <span className="flex flex-wrap items-center gap-2">
                        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${SEV[f.finding.severity] ?? SEV.low}`}>{f.finding.severity}</span>
                        <span className="text-sm font-semibold">{f.finding.issue_type.replace(/_/g, ' ')}</span>
                        <span className="text-xs text-slate-700">at {fmt(f.finding.t_start, 1)}s</span>
                        <span className={`ml-auto text-xs font-semibold ${f.fixed ? 'text-green-900' : 'text-red-900'}`}>{f.fixed ? '✓ fix verified' : '✕ not fixed'}</span>
                      </span>
                      <span className="mt-2 block text-sm"><span className="text-slate-700">Heard: </span><q>{f.finding.announced_text || 'silence'}</q></span>
                      <span className="block text-sm text-slate-800"><span className="text-slate-700">Needed: </span>{f.finding.visible_text_or_description}</span>
                    </button>
                  </li>
                ))}
              </ol>
              {result && result.rejected_unsupported.length > 0 && (
                <details className="rounded-lg border border-slate-300 bg-white p-3 text-sm"><summary className="cursor-pointer font-semibold">Why were {result.rejected_unsupported.length} rejected?</summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5">{result.rejected_unsupported.map((r, i) => <li key={i}>{r.finding.issue_type}: {r.reason}</li>)}</ul></details>
              )}
            </section>

            <section aria-labelledby="h-fix" className="space-y-3">
              <h2 id="h-fix" className="text-lg font-semibold">Patch and verification</h2>
              {!current && <p className="rounded-lg border border-dashed border-slate-400 p-4 text-sm text-slate-700">Select a finding to see its patch.</p>}
              {current && (
                <>
                  <p className="text-sm"><span className="font-semibold">WCAG {current.finding.wcag_guess}</span>{current.citations.length > 0 && <> · cited: <ul className="mt-1 list-disc pl-5">{current.citations.map(c => <li key={c.url}><a href={c.url} target="_blank" rel="noreferrer" className="text-accent underline">{c.title || c.url}<span className="sr-only"> (opens in a new tab)</span></a></li>)}</ul></>}</p>
                  <Diff edits={current.final?.edits ?? []} />
                  {current.final?.rationale && <p className="text-sm text-slate-800">{current.final.rationale}</p>}
                  <div className={`rounded-lg border-2 p-3 text-sm ${current.fixed ? 'border-green-700 bg-green-50 text-green-950' : 'border-red-700 bg-red-50 text-red-950'}`}>
                    <p className="font-semibold">{current.fixed ? '✓ Verified' : '✕ Verification failed'}{current.model_used ? ` · fixed by ${current.model_used}` : ''}{current.attempts.length > 1 ? ` · ${current.attempts.length} attempts` : ''}</p>
                    {current.final?.reason && <p>{current.final.reason}</p>}
                    <ul className="mt-1 list-disc pl-5">{current.final?.verification?.checks.map((c, i) => <li key={i}>{c}</li>)}</ul>
                    <p className="mt-2 text-xs">Verification is a deterministic accessibility-tree proxy for screen-reader output, not a live screen reader.</p>
                  </div>
                  <div role="group" aria-label="Hear it" className="rounded-lg border border-slate-300 bg-white p-3">
                    <p className="mb-2 text-sm font-semibold">Hear it</p>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" onClick={() => play(current.before_audio)} disabled={!current.before_audio} className="rounded-md border border-slate-500 px-3 py-2 text-sm font-semibold hover:bg-slate-100 disabled:text-slate-600">▶ Before</button>
                      <button type="button" onClick={() => play(current.after_audio)} disabled={!current.after_audio} className="rounded-md border border-slate-500 px-3 py-2 text-sm font-semibold hover:bg-slate-100 disabled:text-slate-600">▶ After {current.fixed ? '✓' : '✕'}</button>
                    </div>
                    <p className="mt-2 text-xs text-slate-700">Before: “{current.finding.announced_text || 'silence'}” · After: “{current.final?.verification?.after_announcement || 'n/a'}”</p>
                  </div>
                </>
              )}
            </section>
          </div>
        </section>

        <section id="panel-1" role="tabpanel" aria-labelledby="tab-1" hidden={tab !== 'Benchmark'} className="space-y-4">
          <h2 className="text-lg font-semibold">axe-core alone vs Heard</h2>
          {benchErr && <p className="text-sm">{benchErr}</p>}
          {bench && (
            <>
              <Placeholder source={bench.source.includes('oracle_stub') ? 'oracle_stub' : ''} />
              <dl className="grid max-w-2xl grid-cols-2 gap-3 sm:grid-cols-4">
                {[['axe-core detected', `${bench.axe_detected}/${bench.total_bugs}`], ['Heard detected', `${bench.heard_detected}/${bench.total_bugs}`], ['Fixes verified', `${bench.fixes_verified}/${bench.heard_detected}`], ['Rejected unsupported', String(bench.rejected_unsupported)]].map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-slate-300 bg-white p-3"><dt className="text-xs text-slate-700">{k}</dt><dd className="text-2xl font-bold text-accent-dark">{v}</dd></div>))}
              </dl>
              <div className="overflow-x-auto"><table className="w-full min-w-[640px] border-collapse bg-white text-sm">
                <caption className="sr-only">Per-bug detection results</caption>
                <thead><tr className="bg-slate-100 text-left">{['Bug', 'Site', 'Category', 'axe-core', 'Heard', 'Fix verified'].map(h => <th key={h} scope="col" className="border border-slate-300 px-3 py-2">{h}</th>)}</tr></thead>
                <tbody>{bench.bugs.map(b => <tr key={b.id}>
                  <th scope="row" className="border border-slate-300 px-3 py-2 text-left">{b.id}</th><td className="border border-slate-300 px-3 py-2">{b.site}</td><td className="border border-slate-300 px-3 py-2">{b.category.replace(/_/g, ' ')}</td>
                  {[b.axe_detected, b.heard_detected, b.fix_verified].map((v, i) => <td key={i} className="border border-slate-300 px-3 py-2">{v ? '✓ yes' : '✕ no'}</td>)}</tr>)}</tbody></table></div>
              <p className="max-w-3xl text-xs text-slate-700">{bench.matching_rule}</p>
            </>
          )}
        </section>

        <section id="panel-2" role="tabpanel" aria-labelledby="tab-2" hidden={tab !== 'Cost and models'} className="space-y-4">
          <h2 className="text-lg font-semibold">Cost and models</h2>
          <p aria-live="polite" className="rounded-lg border border-slate-300 bg-white p-3 text-sm" data-testid="live-cost">
            {(running ? liveCost : result?.cost.total) ? <>Calls: <strong>{(running ? liveCost : result?.cost.total)!.calls}</strong> · tokens in/out: <strong>{(running ? liveCost : result?.cost.total)!.input_tokens}/{(running ? liveCost : result?.cost.total)!.output_tokens}</strong> · latency: <strong>{fmt((running ? liveCost : result?.cost.total)!.latency_s, 1)}s</strong> · est. cost: <strong>{money(running ? liveCost! : result?.cost.total)}</strong></> : 'No model calls in this view yet.'}
          </p>
          {result && (['by_stage', 'by_model'] as const).map(k => (
            <div key={k} className="overflow-x-auto"><table className="w-full min-w-[560px] border-collapse bg-white text-sm">
              <caption className="pb-1 text-left font-semibold">{k === 'by_stage' ? 'By stage' : 'By model'}</caption>
              <thead><tr className="bg-slate-100 text-left">{[k === 'by_stage' ? 'Stage' : 'Model', 'Calls', 'Input tokens', 'Output tokens', 'Latency', 'Est. cost'].map(h => <th key={h} scope="col" className="border border-slate-300 px-3 py-2">{h}</th>)}</tr></thead>
              <tbody>{Object.entries(result.cost[k]).map(([name, v]) => <tr key={name}><th scope="row" className="border border-slate-300 px-3 py-2 text-left font-mono text-xs">{name}</th>
                <td className="border border-slate-300 px-3 py-2">{v.calls}</td><td className="border border-slate-300 px-3 py-2">{v.input_tokens}</td><td className="border border-slate-300 px-3 py-2">{v.output_tokens}</td><td className="border border-slate-300 px-3 py-2">{fmt(v.latency_s, 1)}s</td><td className="border border-slate-300 px-3 py-2">{money(v)}</td></tr>)}</tbody></table></div>))}
          {result && Object.keys(result.cost.by_stage).length === 0 && <p className="text-sm text-slate-700">This result was produced without model calls (placeholder), so there is nothing to price.</p>}
        </section>
      </main>
      <footer className="mx-auto max-w-[1400px] px-4 pb-8 text-xs text-slate-700 sm:px-6">MIT licensed · Sessions are simulated screen-reader sessions · Verification is an accessibility-tree proxy.</footer>
    </div>
  )
}
