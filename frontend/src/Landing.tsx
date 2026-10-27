import { useEffect, useRef, useState } from 'react'
import type { Bench, FindingResult, Result } from './types'
import { BTN_PRIMARY, BTN_SECONDARY, Dot, HUE, hue } from './design'
import { ThemeToggle } from './theme'

const REPO = 'https://github.com/WinexWolf/Heard'
const DEMO = '/app/'

const STEPS = [
  { n: 1, hue: HUE.blue, title: 'Listen', body: 'Nemotron Nano Omni reviews the session: what the screen reader said, step by step, against what was on screen. Mismatches come back as structured findings.' },
  { n: 2, hue: HUE.purple, title: 'Ground', body: 'A deterministic check drops any finding whose quote is not in the speech log. Live Tavily search pulls the WCAG technique to cite.' },
  { n: 3, hue: HUE.pink, title: 'Patch', body: 'Nemotron Super writes a minimal search-and-replace edit to the page source, grounded in the cited technique.' },
  { n: 4, hue: HUE.green, title: 'Verify', body: 'No model here. The patched page loads in Chromium, the accessibility tree is checked, and axe-core must report no new violations. One repair, then Nemotron Ultra, if it fails.' },
]

const STACK = [
  { name: 'Nebius Token Factory', dot: HUE.teal.dot },
  { name: 'NVIDIA Nemotron Nano Omni, Super, Ultra', dot: HUE.green.dot },
  { name: 'Tavily search', dot: HUE.indigo.dot },
  { name: 'Playwright and Chromium', dot: HUE.blue.dot },
  { name: 'axe-core', dot: HUE.orange.dot },
  { name: 'FastAPI and React', dot: HUE.purple.dot },
]

function useAudio() {
  const ref = useRef<HTMLAudioElement | null>(null)
  return (path: string) => { ref.current?.pause(); ref.current = new Audio(`/media/${path}`); void ref.current.play() }
}

function HearTheDifference() {
  const [example, setExample] = useState<FindingResult | null>(null)
  const play = useAudio()
  useEffect(() => {
    fetch('/api/sessions/shop_buggy/result').then(r => (r.ok ? r.json() : Promise.reject(r)))
      .then((r: Result) => setExample(r.findings.find(f => f.fixed && f.before_audio && f.after_audio && f.finding.issue_type === 'missing_name')
        ?? r.findings.find(f => f.fixed && f.before_audio && f.after_audio) ?? null))
      .catch(() => setExample(null))
  }, [])

  const rows = example ? [
    { label: 'Before', tint: 'bg-red/10 text-red-text', heard: example.finding.announced_text || 'silence', audio: example.before_audio! },
    { label: 'After', tint: 'bg-green/10 text-green-text', heard: example.final?.verification?.after_announcement || '', audio: example.after_audio! },
  ] : []

  return (
    <section aria-labelledby="h-hear" className="glass space-y-2 rounded-xl p-3">
      <h2 id="h-hear" className="text-title2">Hear the difference</h2>
      {!example && <p className="text-callout">Open the demo to hear before-and-after audio for each finding.</p>}
      {example && (
        <>
          <p className="text-callout">A screen-reader user tabs to the cart in the demo shop. This is what they hear, before and after the verified fix.</p>
          <ul className="space-y-1">
            {rows.map(r => (
              <li key={r.label} className="flex flex-wrap items-center gap-2 rounded-lg bg-card p-2 shadow">
                <span className={`rounded-full px-1.5 text-caption leading-6 font-semibold ${r.tint}`}>{r.label}</span>
                <q className="min-w-0 flex-1 text-headline">{r.heard}</q>
                <button type="button" onClick={() => play(r.audio)} className={r.label === 'After' ? BTN_PRIMARY : BTN_SECONDARY}>
                  <span aria-hidden="true">▶ </span>Play<span className="sr-only"> {r.label.toLowerCase()} audio</span></button>
              </li>
            ))}
          </ul>
          <p className="text-footnote">Audio from a simulated screen reader. The after clip is recorded from the patched page once verification passes.</p>
        </>
      )}
    </section>
  )
}

function WhatLintersMiss() {
  const [bench, setBench] = useState<Bench | null>(null)
  useEffect(() => { fetch('/api/benchmark').then(r => (r.ok ? r.json() : Promise.reject(r))).then(setBench).catch(() => setBench(null)) }, [])
  if (!bench) return null
  const missed = bench.bugs.filter(b => !b.axe_detected)
  return (
    <section id="gap" aria-labelledby="h-gap" className="scroll-mt-8 space-y-3">
      <div className="max-w-3xl space-y-1">
        <h2 id="h-gap" className="text-title">What linters miss</h2>
        <p className="text-body">We seeded {bench.total_bugs} accessibility bugs across three small sites and ran axe-core on them. It caught {bench.axe_detected}. The rest are the kind you notice by listening.</p>
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <div className="glass space-y-1 self-start rounded-xl p-3">
          <p className="text-largeTitle text-orange-text">{bench.axe_detected}/{bench.total_bugs}</p>
          <p className="text-headline">seeded bugs caught by axe-core alone</p>
          <p className="text-footnote">Measured with axe-core on the demo sites, not asserted.</p>
        </div>
        <ul className="grid gap-1 sm:grid-cols-2 lg:col-span-2">
          {missed.map(b => (
            <li key={b.id} className="surface space-y-1 p-2">
              <span className={`inline-flex items-baseline gap-1 rounded-full px-1.5 text-caption leading-6 font-semibold ${hue(b.category).tint}`}>
                <Dot className={hue(b.category).dot} />{b.category.replace(/_/g, ' ')}</span>
              <p className="text-callout">{b.description}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

export default function Landing() {
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-1 focus:top-1 focus:z-50 focus:rounded-sm focus:bg-card focus:px-2 focus:py-1">Skip to content</a>
      <header className="glass sticky top-0 z-40 border-x-0 border-t-0">
        <div className="mx-auto flex max-w-page items-center justify-between gap-2 px-2 py-1 sm:px-3">
          <a href="/" className="text-title3 text-ink no-underline hover:underline">Heard</a>
          <nav aria-label="Primary" className="flex items-center gap-1">
            <ul className="hidden gap-1 md:flex">
              {[['How it works', '#how'], ['What linters miss', '#gap'], ['Built with', '#stack']].map(([label, href]) => (
                <li key={href}><a href={href} className="inline-block min-h-tap rounded-sm px-1.5 py-1.5 text-callout text-ink no-underline hover:bg-ink/5">{label}</a></li>
              ))}
            </ul>
            <a href={DEMO} className={`hidden sm:inline-block ${BTN_PRIMARY}`}>Open the demo</a>
            <ThemeToggle />
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-page space-y-8 px-2 py-6 sm:px-3">
        <section aria-labelledby="h-hero" className="grid items-center gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <span className="inline-flex items-baseline gap-1 rounded-full bg-card px-1.5 text-caption leading-6 font-semibold text-blue-text shadow">
              <Dot className="bg-blue" />Accessibility audits by listening</span>
            <h1 id="h-hero" className="text-largeTitle tracking-tight">Linters read your code. Heard listens to your product.</h1>
            <p className="max-w-xl text-body">
              Heard takes a screen-reader session and finds the places where what a blind user hears does not match what is on screen.
              Then it patches the source, cites the WCAG technique, and proves the fix in a real browser.
            </p>
            <div className="flex flex-wrap gap-1">
              <a href={DEMO} className={BTN_PRIMARY}>Open the demo</a>
              <a href={REPO} className={BTN_SECONDARY}>View source on GitHub</a>
            </div>
            <p className="text-footnote">No sign-in. Cached demo results load instantly.</p>
          </div>
          <HearTheDifference />
        </section>

        <section id="how" aria-labelledby="h-how" className="scroll-mt-8 space-y-3">
          <div className="max-w-3xl space-y-1">
            <h2 id="h-how" className="text-title">How it works</h2>
            <p className="text-body">Four stages per finding. Models do the listening and the writing; the checking is deterministic.</p>
          </div>
          <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map(s => (
              <li key={s.n} className="surface space-y-1 p-2">
                <span className={`inline-block rounded-full px-1.5 text-caption leading-6 font-semibold ${s.hue.tint}`}>Step {s.n}</span>
                <h3 className="text-title2">{s.title}</h3>
                <p className="text-callout">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <WhatLintersMiss />

        <section id="stack" aria-labelledby="h-stack" className="scroll-mt-8 space-y-3">
          <h2 id="h-stack" className="text-title">Built with</h2>
          <ul className="flex flex-wrap gap-1">
            {STACK.map(s => (
              <li key={s.name} className="inline-flex items-baseline gap-1 rounded-full bg-card px-2 text-callout leading-6 shadow">
                <span className="leading-8"><Dot className={s.dot} /></span>{s.name}</li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="h-try" className="glass space-y-2 rounded-xl p-3">
          <h2 id="h-try" className="text-title2">Try it on the demo sessions</h2>
          <p className="max-w-2xl text-body">Three recorded sessions, twelve seeded bugs. Watch the recording, read each finding, see the patch, and play the before and after.</p>
          <a href={DEMO} className={BTN_PRIMARY}>Open the demo</a>
        </section>
      </main>

      <footer className="mx-auto max-w-page space-y-1 px-2 pb-4 text-footnote sm:px-3">
        <p><a href={REPO}>GitHub</a> · MIT licensed</p>
        <p>Sessions are simulated screen-reader sessions. Verification is an accessibility-tree proxy, not a live screen reader.</p>
      </footer>
    </div>
  )
}
