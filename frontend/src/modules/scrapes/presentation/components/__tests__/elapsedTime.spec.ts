import { describe, expect, it } from 'vitest'
import { formatElapsedTime } from '@/modules/scrapes/presentation/components/elapsedTime'

const STARTED_AT = '2026-11-01T10:00:00+00:00'
const STARTED_MS = Date.parse(STARTED_AT)

describe('formatElapsedTime', () => {
  it('shows minutes and seconds since the start', () => {
    expect(formatElapsedTime(STARTED_AT, STARTED_MS + 83_000)).toBe('01:23')
  })

  it('shows 00:00 right at the start', () => {
    expect(formatElapsedTime(STARTED_AT, STARTED_MS)).toBe('00:00')
  })

  it('never goes below zero when the clock is behind the server', () => {
    expect(formatElapsedTime(STARTED_AT, STARTED_MS - 5_000)).toBe('00:00')
  })

  it('shows 00:00 for a start time it cannot read', () => {
    expect(formatElapsedTime('not a date', STARTED_MS)).toBe('00:00')
  })

  it('keeps counting past an hour in minutes', () => {
    expect(formatElapsedTime(STARTED_AT, STARTED_MS + 3_725_000)).toBe('62:05')
  })
})
