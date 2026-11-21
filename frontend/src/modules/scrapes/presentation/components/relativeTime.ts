const SECOND_MS = 1000
const MINUTE_MS = 60 * SECOND_MS
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS
const WEEK_MS = 7 * DAY_MS
const MONTH_MS = 30 * DAY_MS
const YEAR_MS = 365 * DAY_MS

const JUST_NOW = 'just now'
const RELATIVE_LOCALE = 'en'
const ISO_PATTERN =
  /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}(?::?\d{2})?)?)?$/

interface UnitStep {
  unit: Intl.RelativeTimeFormatUnit
  ms: number
}

const UNIT_STEPS: readonly UnitStep[] = [
  { unit: 'year', ms: YEAR_MS },
  { unit: 'month', ms: MONTH_MS },
  { unit: 'week', ms: WEEK_MS },
  { unit: 'day', ms: DAY_MS },
  { unit: 'hour', ms: HOUR_MS },
  { unit: 'minute', ms: MINUTE_MS },
]

const relativeFormat = new Intl.RelativeTimeFormat(RELATIVE_LOCALE, { numeric: 'always' })
const exactFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function parseIso(iso: string): Date | null {
  const text = iso.trim()
  if (!ISO_PATTERN.test(text)) {
    return null
  }
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatRelativeTime(iso: string, now: Date): string | null {
  const date = parseIso(iso)
  if (date === null) {
    return null
  }
  const elapsedMs = now.getTime() - date.getTime()
  const step = UNIT_STEPS.find(({ ms }) => Math.abs(elapsedMs) >= ms)
  if (step === undefined) {
    return JUST_NOW
  }
  return relativeFormat.format(-Math.trunc(elapsedMs / step.ms), step.unit)
}

export function formatExactTime(iso: string): string | null {
  const date = parseIso(iso)
  return date === null ? null : exactFormat.format(date)
}
