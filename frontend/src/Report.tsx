import type { CostAgg, Finding } from './types'
import { Dot, hue } from './design'
import { ThemeToggle } from './theme'

const REPO = 'https://github.com/WinexWolf/Heard'
const SEVERITY = ['low', 'medium', 'high', 'critical']
const SEV: Record<string, string> = { critical: 'bg-red/10 text-red-text', high: 'bg-orange/10 text-orange-text', medium: 'bg-ink/5 text-ink', low: 'bg-ink/5 text-muted' }

interface Fix {
  status: 'fixed' | 'already_fixed' | 'failed' | 'no_source'; kept?: boolean; model?: string | null; files?: string[]
  diff?: string; reason?: string; after_announcement?: string; attempts: unknown[]
}

interface Report {
  result: 'pass' | 'fail' | 'unaudited'; url: string; base?: string; generated_at?: string; fail_on: string
  pages: Record<string, { status: string; changed_steps: number; lines: [string, string][] }>
  changed_steps: number; findings: (Finding & { page: string; step: string; fix?: Fix })[]; failing: number
  rejected_unsupported: { page: string; finding: Finding; reason: string }[]; model_calls: number; cost: CostAgg | null
}

// heard check injects the report JSON into this element (see heard/app/report.py).
function readReport(): Report | null {
  try { return JSON.parse(document.getElementById('heard-data')?.textContent ?? '') } catch { return null }
}

// Sits on the gradient backdrop, so a solid card pill: a 10% tint over the backdrop drops below 4.5:1.
const STATUS = {
  pass: { icon: '✓', tint: 'bg-card text-success-text shadow', label: 'Passed' },
  fail: { icon: '✕', tint: 'bg-card text-destructive-text shadow', label: 'Failed' },
  unaudited: { icon: '⚠', tint: 'bg-card text-warning-text shadow', label: 'Not audited' },
}
const PAGE_STATUS: Record<string, string> = { changed: 'bg-blue/10 text-blue-text', new: 'bg-purple/10 text-purple-text', removed: 'bg-red/10 text-red-text' }

function headline(r: Report) {
  if (r.result === 'fail') return `${r.failing} accessibility regression${r.failing === 1 ? '' : 's'}`
  if (r.result === 'unaudited') return 'Speech changed, not yet audited'
  return r.changed_steps ? 'No accessibility regressions' : 'Nothing users hear changed'
}

const FIX_STATUS: Record<Fix['status'], { tint: string; label: string }> = {
  fixed: { tint: 'bg-success/10 text-success-text', label: '✓ Fixed and verified' },
  already_fixed: { tint: 'bg-success/10 text-success-text', label: '✓ Already fixed' },
  failed: { tint: 'bg-destructive/10 text-destructive-text', label: '✕ Not fixed' },
  no_source: { tint: 'bg-warning/10 text-warning-text', label: '⚠ Source not found' },
}

function UnifiedDiff({ diff }: { diff: string }) {
  return (
    <pre className="overflow-x-auto rounded-md border font-mono text-footnote">
      {diff.trimEnd().split('\n').map((l, i) => (
        <span key={i} className={`block whitespace-pre-wrap break-words px-1.5 ${l.startsWith('+') && !l.startsWith('+++') ? 'bg-green/10'
          : l.startsWith('-') && !l.startsWith('---') ? 'bg-red/10' : l.startsWith('@@') ? 'bg-bg text-muted' : ''}`}>{l || ' '}</span>
      ))}
    </pre>
  )
}

function FixResult({ fix }: { fix: Fix }) {
  const st = FIX_STATUS[fix.status]
  return (
    <div className="space-y-1 border-t pt-1">
      <p className="flex flex-wrap items-baseline gap-1">
        <Pill tint={st.tint}>{st.label}</Pill>
        {fix.status === 'fixed' && <span className="text-footnote text-muted">{fix.files?.join(', ')} · {fix.model ?? 'model'} · {fix.attempts.length} attempt(s){fix.kept ? '' : ' · dry run, not applied'}</span>}
      </p>
      {fix.status === 'fixed' && fix.after_announcement && <p className="text-callout"><span className="text-muted">Now heard: </span><q>{fix.after_announcement}</q></p>}
      {fix.diff && <UnifiedDiff diff={fix.diff} />}
      {fix.status !== 'fixed' && fix.reason && <p className="text-footnote">{fix.reason}</p>}
    </div>
  )
}

function Pill({ tint, children }: { tint: string; children: React.ReactNode }) {
  return <span className={`inline-block rounded-full px-1.5 text-caption leading-6 font-semibold ${tint}`}>{children}</span>
}

export default function ReportPage() {
  const r = readReport()
  const pagesChanged = r ? Object.values(r.pages).filter(p => p.status !== 'same').length : 0
  const s = r ? STATUS[r.result] : null
  const fixes = r ? r.findings.flatMap(f => (f.fix ? [f.fix] : [])) : []
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-1 focus:top-1 focus:z-50 focus:rounded-sm focus:bg-card focus:px-2 focus:py-1">Skip to content</a>
      <header className="glass sticky top-0 z-40 border-x-0 border-t-0">
        <div className="mx-auto flex max-w-page items-center justify-between gap-2 px-2 py-1 sm:px-3">
          <p className="text-title3"><a href={REPO} className="text-ink no-underline hover:underline">Heard</a> <span className="text-callout font-normal">accessibility report</span></p>
          <ThemeToggle />
        </div>
      </header>

      <main id="main" className="mx-auto max-w-page space-y-6 px-2 py-4 sm:px-3">
        {!r || !s ? (
          <section className="surface space-y-1 p-3">
            <h1 className="text-title">No report data</h1>
            <p className="text-callout">This page is filled in by <code>heard check</code>. Run it, then open <code>.heard/report.html</code> or run <code>heard report</code>.</p>
          </section>
        ) : (
          <>
            <section aria-labelledby="h-summary" className="space-y-3">
              <div className="space-y-1">
                <Pill tint={s.tint}><span aria-hidden="true">{s.icon} </span>{s.label}</Pill>
                <h1 id="h-summary" className="text-largeTitle tracking-tight">{headline(r)}</h1>
                <p className="max-w-3xl text-callout">
                  {Object.keys(r.pages).length} page(s) of <code>{r.url}</code> compared with <code>{r.base ?? 'the baseline'}</code>
                  {r.generated_at ? ` · ${r.generated_at.replace('T', ' ')}` : ''} · fails on <strong>{r.fail_on}</strong> or worse
                </p>
                {fixes.length > 0 && <p className="text-callout"><code>heard fix</code>: {fixes.filter(x => x.status === 'fixed' || x.status === 'already_fixed').length} of {fixes.length} fixed and verified on the running app.</p>}
              </div>
              <dl className="grid max-w-3xl grid-cols-2 gap-2 sm:grid-cols-4">
                {([['Regressions', String(r.failing), r.failing ? 'text-destructive-text' : 'text-success-text'],
                   ['Announcements changed', String(r.changed_steps), 'text-accent-text'],
                   ['Pages changed', String(pagesChanged), 'text-purple-text'],
                   ['Model calls', String(r.model_calls), 'text-teal-text']] as const).map(([k, v, c]) => (
                  <div key={k} className="glass space-y-1 rounded-lg p-2"><dt className="text-subheadline">{k}</dt><dd className={`text-title ${c}`}>{v}</dd></div>))}
              </dl>
              {r.result === 'unaudited' && (
                <p role="note" className="max-w-3xl rounded-lg border border-l-4 border-l-warning bg-card p-2 text-callout shadow">
                  <strong className="text-warning-text"><span aria-hidden="true">⚠ </span>No model key.</strong> Set <code>NEBIUS_API_KEY</code>, <code>NEBIUS_BASE_URL</code> and{' '}
                  <code>MODEL_PERCEPTION</code> so Heard can judge these changes. The speech diff below is accurate either way.
                </p>
              )}
            </section>

            {r.findings.length > 0 && (
              <section aria-labelledby="h-findings" className="space-y-2">
                <h2 id="h-findings" className="text-title">Regressions</h2>
                <ol className="grid items-start gap-2 lg:grid-cols-2">
                  {r.findings.map((f, i) => {
                    const fails = SEVERITY.indexOf(f.severity) >= SEVERITY.indexOf(r.fail_on)
                    return (
                      <li key={i} className={`surface space-y-1 border-l-4 p-2 ${hue(f.issue_type).bar}`}>
                        <p className="flex flex-wrap items-baseline gap-1">
                          <span className="text-headline">{f.issue_type.replace(/_/g, ' ')}</span>
                          <Pill tint={SEV[f.severity] ?? SEV.low}>{f.severity}</Pill>
                          {fails && <Pill tint="bg-destructive/10 text-destructive-text">fails the check</Pill>}
                        </p>
                        <p className="font-mono text-footnote text-muted">{f.page}</p>
                        <p className="text-callout"><span className="text-muted">Heard: </span><q>{f.announced_text || 'silence'}</q></p>
                        <p className="text-callout"><span className="text-muted">Needed: </span>{f.visible_text_or_description}</p>
                        <p className="flex items-baseline gap-1 text-footnote text-muted"><Dot className={hue(f.issue_type).dot} />WCAG {f.wcag_guess}{f.evidence ? ` · ${f.evidence}` : ''}</p>
                        {f.fix && <FixResult fix={f.fix} />}
                      </li>
                    )
                  })}
                </ol>
              </section>
            )}

            <section aria-labelledby="h-speech" className="space-y-2">
              <h2 id="h-speech" className="text-title">What screen-reader users will hear differently</h2>
              {pagesChanged === 0 && <p className="text-callout">Every announcement matches the baseline.</p>}
              <div className="grid items-start gap-2 lg:grid-cols-2">
                {Object.entries(r.pages).filter(([, p]) => p.status !== 'same').map(([key, p]) => (
                  <section key={key} aria-label={key} className="surface space-y-1 p-2">
                    <h3 className="flex flex-wrap items-baseline gap-1">
                      <span className="font-mono text-headline">{key}</span>
                      <Pill tint={PAGE_STATUS[p.status] ?? SEV.low}>{p.status}</Pill>
                      <span className="text-footnote text-muted">{p.changed_steps} step(s)</span>
                    </h3>
                    {p.status === 'new' && <p className="text-callout text-muted">New in this push: every step was audited.</p>}
                    {p.status === 'removed' && <p className="text-callout text-muted">This page is no longer scanned.</p>}
                    {p.lines.map(([before, after], i) => (
                      <div key={i} className="overflow-hidden rounded-md border text-callout">
                        <p className="bg-red/10 px-1.5 py-1"><span aria-label="before" className="font-semibold text-red-text">− </span>{before || '(nothing)'}</p>
                        <p className="bg-green/10 px-1.5 py-1"><span aria-label="after" className="font-semibold text-green-text">+ </span>{after || '(nothing)'}</p>
                      </div>
                    ))}
                  </section>
                ))}
              </div>
            </section>

            {r.rejected_unsupported.length > 0 && (
              <details className="surface p-2 text-callout">
                <summary className="cursor-pointer font-semibold">{r.rejected_unsupported.length} finding(s) dropped by the evidence check</summary>
                <ul className="mt-1 list-disc space-y-1 pl-3">{r.rejected_unsupported.map((x, i) => <li key={i}><code>{x.page}</code> {x.finding.issue_type}: {x.reason}</li>)}</ul>
              </details>
            )}
          </>
        )}
      </main>
      <footer className="mx-auto max-w-page px-2 pb-4 text-footnote sm:px-3">
        Generated by <code>heard check</code>. Announcements are built from the browser accessibility tree, not a live screen reader.
      </footer>
    </div>
  )
}
