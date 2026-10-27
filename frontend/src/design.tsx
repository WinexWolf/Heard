// Shared UI pieces for the landing page and the app (class names spelled out so Tailwind keeps them).

export const HUE = {
  blue: { dot: 'bg-blue', bar: 'border-l-blue', tint: 'bg-blue/10 text-blue-text' },
  indigo: { dot: 'bg-indigo', bar: 'border-l-indigo', tint: 'bg-indigo/10 text-indigo-text' },
  purple: { dot: 'bg-purple', bar: 'border-l-purple', tint: 'bg-purple/10 text-purple-text' },
  pink: { dot: 'bg-pink', bar: 'border-l-pink', tint: 'bg-pink/10 text-pink-text' },
  orange: { dot: 'bg-orange', bar: 'border-l-orange', tint: 'bg-orange/10 text-orange-text' },
  teal: { dot: 'bg-teal', bar: 'border-l-teal', tint: 'bg-teal/10 text-teal-text' },
  green: { dot: 'bg-green', bar: 'border-l-green', tint: 'bg-green/10 text-green-text' },
}

// One stable colour per issue family.
const CATEGORY: Record<string, keyof typeof HUE> = {
  missing_name: 'blue', missing_alt: 'blue', missing_label: 'blue', label_in_name: 'blue',
  vague_link: 'indigo', repeated_control: 'indigo', other: 'indigo',
  div_button: 'purple', missing_state: 'purple', tab_widget: 'purple',
  modal_dialog: 'pink', error_not_announced: 'orange', heading_skip: 'teal',
}
export const hue = (issue: string) => HUE[CATEGORY[issue] ?? 'indigo']

const BTN = 'inline-block min-h-tap rounded-sm px-2 py-1.5 text-callout font-semibold no-underline disabled:cursor-not-allowed'
export const BTN_PRIMARY = `${BTN} bg-accent-fill text-white shadow hover:bg-accent-strong disabled:bg-card disabled:text-muted disabled:shadow-none`
export const BTN_SECONDARY = `${BTN} border bg-card text-accent-text hover:bg-accent/10 disabled:text-muted`

export function Dot({ className }: { className: string }) {
  return <span aria-hidden="true" className={`inline-block h-1 w-1 shrink-0 rounded-full ${className}`} />
}
