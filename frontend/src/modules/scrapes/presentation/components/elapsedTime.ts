const SECOND_MS = 1000
const SECONDS_PER_MINUTE = 60
const PAD_LENGTH = 2

export function formatElapsedTime(startedAt: string, now: number): string {
  const startedMs = Date.parse(startedAt)
  if (Number.isNaN(startedMs)) {
    return '00:00'
  }
  const totalSeconds = Math.max(0, Math.floor((now - startedMs) / SECOND_MS))
  const minutes = Math.floor(totalSeconds / SECONDS_PER_MINUTE)
  const seconds = totalSeconds % SECONDS_PER_MINUTE
  return `${padTimeUnit(minutes)}:${padTimeUnit(seconds)}`
}

function padTimeUnit(value: number): string {
  return String(value).padStart(PAD_LENGTH, '0')
}
