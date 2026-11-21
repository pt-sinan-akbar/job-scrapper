import { describe, expect, it } from 'vitest'
import {
  formatExactTime,
  formatRelativeTime,
} from '@/modules/scrapes/presentation/components/relativeTime'

const NOW = new Date('2026-11-19T12:00:00+00:00')

describe('formatRelativeTime', () => {
  it.each([
    ['2026-11-19T12:00:00+00:00', 'just now'],
    ['2026-11-19T11:59:01+00:00', 'just now'],
    ['2026-11-19T11:59:00+00:00', '1 minute ago'],
    ['2026-11-19T11:15:00+00:00', '45 minutes ago'],
    ['2026-11-19T11:00:01+00:00', '59 minutes ago'],
    ['2026-11-19T11:00:00+00:00', '1 hour ago'],
    ['2026-11-18T12:00:01+00:00', '23 hours ago'],
    ['2026-11-18T12:00:00+00:00', '1 day ago'],
    ['2026-11-18T10:21:43+00:00', '1 day ago'],
    ['2026-11-13T12:00:00+00:00', '6 days ago'],
    ['2026-11-12T12:00:00+00:00', '1 week ago'],
    ['2026-10-22T12:00:00+00:00', '4 weeks ago'],
    ['2026-10-20T12:00:00+00:00', '1 month ago'],
    ['2025-12-01T12:00:00+00:00', '11 months ago'],
    ['2025-11-19T12:00:00+00:00', '1 year ago'],
    ['2023-11-19T12:00:00+00:00', '3 years ago'],
  ])('describes %s as %s', (iso, expected) => {
    expect(formatRelativeTime(iso, NOW)).toBe(expected)
  })

  it('reads the offset in the timestamp instead of the machine timezone', () => {
    expect(formatRelativeTime('2026-11-18T17:21:43+07:00', NOW)).toBe('1 day ago')
    expect(formatRelativeTime('2026-11-18T10:21:43Z', NOW)).toBe('1 day ago')
  })

  it('accepts a date without a time', () => {
    expect(formatRelativeTime('2026-11-17', NOW)).toBe('2 days ago')
  })

  it('treats a timestamp slightly ahead of now as just now', () => {
    expect(formatRelativeTime('2026-11-19T12:00:20+00:00', NOW)).toBe('just now')
  })

  it('describes a timestamp further ahead as upcoming', () => {
    expect(formatRelativeTime('2026-11-19T15:00:00+00:00', NOW)).toBe('in 3 hours')
  })

  it.each(['2 days ago', 'Posted 2', '', 'yesterday', '2026-13-45T99:00:00Z', '20261118'])(
    'returns null for %j',
    (text) => {
      expect(formatRelativeTime(text, NOW)).toBeNull()
    },
  )
})

describe('formatExactTime', () => {
  it('writes the date and the time of day', () => {
    const exact = formatExactTime('2026-06-15T12:00:00+00:00')

    expect(exact).toContain('2026')
    expect(exact).toMatch(/\d{1,2}[:.]\d{2}/)
  })

  it('gives the same text for the same instant in another offset', () => {
    expect(formatExactTime('2026-06-15T19:00:00+07:00')).toBe(
      formatExactTime('2026-06-15T12:00:00+00:00'),
    )
  })

  it('tells two instants apart', () => {
    expect(formatExactTime('2026-06-15T12:00:00+00:00')).not.toBe(
      formatExactTime('2026-06-15T13:30:00+00:00'),
    )
  })

  it.each(['2 days ago', '', 'Posted 2'])('returns null for %j', (text) => {
    expect(formatExactTime(text)).toBeNull()
  })
})
