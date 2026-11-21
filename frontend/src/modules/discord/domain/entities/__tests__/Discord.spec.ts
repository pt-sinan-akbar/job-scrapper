import { describe, expect, it } from 'vitest'
import {
  countChars,
  fillTemplate,
  hasSettingsChanges,
  MAX_MESSAGE_CHARS,
  SAMPLE_JOB,
  toMentionPrefix,
  toSampleMessage,
  toSendSummary,
  toSettingsChanges,
  toSettingsForm,
  type DiscordSettings,
} from '@/modules/discord/domain/entities/Discord'

const JOB_FIELDS = [
  'site',
  'matched_keyword',
  'title',
  'company',
  'company_id',
  'url',
  'location',
  'salary',
  'salary_min',
  'salary_max',
  'posted_date',
  'posted_at',
  'work_type',
  'employment_type',
  'experience_level',
  'job_id',
  'requirements',
]

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: null,
  messageTemplate: '{title} at {company}',
  maxChars: 1900,
  updatedAt: '2026-11-11T01:00:00+00:00',
}

describe('toSettingsForm', () => {
  it('turns every value into text and leaves the token empty', () => {
    expect(toSettingsForm(SETTINGS)).toEqual({
      token: '',
      defaultChannelId: '12345678901234567',
      mentionUserId: '',
      messageTemplate: '{title} at {company}',
      maxChars: '1900',
    })
  })
})

describe('toSettingsChanges', () => {
  it('sends nothing when the form is the same as the saved settings', () => {
    const changes = toSettingsChanges(toSettingsForm(SETTINGS), SETTINGS)

    expect(changes).toEqual({})
  })

  it('leaves the token out when its box is empty', () => {
    const changes = toSettingsChanges(toSettingsForm(SETTINGS), SETTINGS)

    expect(changes).not.toHaveProperty('token')
  })

  it('leaves the token out when its box only has spaces', () => {
    const changes = toSettingsChanges({ ...toSettingsForm(SETTINGS), token: '   ' }, SETTINGS)

    expect(changes).not.toHaveProperty('token')
  })

  it('sends only a typed token without the spaces around it', () => {
    const changes = toSettingsChanges({ ...toSettingsForm(SETTINGS), token: ' abc.def ' }, SETTINGS)

    expect(changes).toEqual({ token: 'abc.def' })
  })

  it('sends null for a cleared channel or user id', () => {
    const settings = { ...SETTINGS, mentionUserId: '76543210987654321' }
    const changes = toSettingsChanges(
      { ...toSettingsForm(settings), defaultChannelId: '  ', mentionUserId: '' },
      settings,
    )

    expect(changes).toEqual({ defaultChannelId: null, mentionUserId: null })
  })

  it('leaves an id out when it was empty and still is', () => {
    const changes = toSettingsChanges(
      { ...toSettingsForm(SETTINGS), mentionUserId: '  ' },
      SETTINGS,
    )

    expect(changes).not.toHaveProperty('mentionUserId')
  })

  it('leaves an id out when only the spaces around it differ', () => {
    const changes = toSettingsChanges(
      { ...toSettingsForm(SETTINGS), defaultChannelId: ' 12345678901234567 ' },
      SETTINGS,
    )

    expect(changes).toEqual({})
  })

  it('sends only the template when only the template changed', () => {
    const changes = toSettingsChanges(
      { ...toSettingsForm(SETTINGS), messageTemplate: '{title}' },
      SETTINGS,
    )

    expect(changes).toEqual({ messageTemplate: '{title}' })
  })

  it('sends only max chars when only max chars changed', () => {
    const changes = toSettingsChanges({ ...toSettingsForm(SETTINGS), maxChars: '1500' }, SETTINGS)

    expect(changes).toEqual({ maxChars: 1500 })
  })

  it('sends every field that changed', () => {
    const changes = toSettingsChanges(
      {
        token: 'abc.def',
        defaultChannelId: '22345678901234567',
        mentionUserId: '76543210987654321',
        messageTemplate: '{title}',
        maxChars: '1500',
      },
      SETTINGS,
    )

    expect(changes).toEqual({
      token: 'abc.def',
      defaultChannelId: '22345678901234567',
      mentionUserId: '76543210987654321',
      messageTemplate: '{title}',
      maxChars: 1500,
    })
  })
})

describe('toMentionPrefix', () => {
  it('is the user tag and a new line when mention is on', () => {
    expect(toMentionPrefix('76543210987654321', true)).toBe('<@76543210987654321>\n')
  })

  it('is empty when mention is off or there is no user id', () => {
    expect(toMentionPrefix('76543210987654321', false)).toBe('')
    expect(toMentionPrefix(null, true)).toBe('')
  })
})

describe('countChars', () => {
  it('counts a character outside the basic plane once', () => {
    expect(countChars('a😀b')).toBe(3)
  })
})

describe('toSendSummary', () => {
  it('names the sent messages when none failed', () => {
    expect(toSendSummary({ sent: 3, failed: 0, results: [] })).toBe('Sent 3 messages')
    expect(toSendSummary({ sent: 1, failed: 0, results: [] })).toBe('Sent 1 message')
  })

  it('names the failed messages too', () => {
    expect(toSendSummary({ sent: 2, failed: 1, results: [] })).toBe('Sent 2, 1 failed')
  })

  it('says nothing was sent when all failed', () => {
    expect(toSendSummary({ sent: 0, failed: 2, results: [] })).toBe('Nothing was sent, 2 failed')
  })
})

describe('hasSettingsChanges', () => {
  it('is false when the form is the same as the saved settings', () => {
    expect(hasSettingsChanges(toSettingsForm(SETTINGS), SETTINGS)).toBe(false)
  })

  it('is false when the token box only has spaces', () => {
    expect(hasSettingsChanges({ ...toSettingsForm(SETTINGS), token: '  ' }, SETTINGS)).toBe(false)
  })

  it.each([
    ['token', 'abc.def'],
    ['defaultChannelId', '22345678901234567'],
    ['mentionUserId', '76543210987654321'],
    ['messageTemplate', '{title}'],
    ['maxChars', '1500'],
  ])('is true when %s differs', (field, text) => {
    expect(hasSettingsChanges({ ...toSettingsForm(SETTINGS), [field]: text }, SETTINGS)).toBe(true)
  })
})

describe('fillTemplate', () => {
  it('puts the job text where each placeholder is', () => {
    expect(fillTemplate('{title} at {company}', { title: 'Engineer', company: 'Acme' })).toBe(
      'Engineer at Acme',
    )
  })

  it('fills a placeholder every time it repeats', () => {
    expect(fillTemplate('{title}, {title}!', { title: 'Engineer' })).toBe('Engineer, Engineer!')
  })

  it('turns a number into text', () => {
    expect(fillTemplate('From {salary_min}', { salary_min: 7000000 })).toBe('From 7000000')
  })

  it('puts a dash for a null, missing, blank or unknown field', () => {
    expect(
      fillTemplate('[{salary}][{location}][{company}][{nope}]', { salary: null, company: '  ' }),
    ).toBe('[-][-][-][-]')
  })

  it('keeps zero as a value', () => {
    expect(fillTemplate('{salary_min}', { salary_min: 0 })).toBe('0')
  })

  it('puts a dash for a name that only exists on every object', () => {
    expect(fillTemplate('[{constructor}][{toString}]', { title: 'Engineer' })).toBe('[-][-]')
  })

  it('fills a name with an underscore, a digit or a letter outside ASCII like the server', () => {
    expect(fillTemplate('{_a1}{naïve}', { _a1: 'x' })).toBe('x-')
  })

  it.each([['{}'], ['{1st}'], ['{ title }'], ['{job-id}'], ['{title'], ['title}'], ['{a.b}']])(
    'leaves %s alone because it is not a valid name',
    (text) => {
      expect(fillTemplate(text, { title: 'Engineer' })).toBe(text)
    },
  )

  it('fills the inner placeholder of doubled braces', () => {
    expect(fillTemplate('{{title}}', { title: 'Engineer' })).toBe('{Engineer}')
  })

  it('does not fill a placeholder that came from a job text', () => {
    expect(fillTemplate('{title}', { title: '{company}', company: 'Acme' })).toBe('{company}')
  })
})

describe('SAMPLE_JOB', () => {
  it.each(JOB_FIELDS)('has a text or a number for %s', (field) => {
    const sample = SAMPLE_JOB[field]

    expect(sample === null || sample === undefined || sample === '').toBe(false)
  })

  it('lists five requirements as markdown bullets', () => {
    const bullets = String(SAMPLE_JOB.requirements)
      .split('\n')
      .filter((line) => line.startsWith('- '))

    expect(bullets).toHaveLength(5)
  })
})

describe('toSampleMessage', () => {
  it('fills the template with the sample job', () => {
    expect(toSampleMessage('{title} at {company}')).toBe(
      'IoT Solution Engineer (Fullstack IoT) at PT Onesia Nusantara Evolusioner',
    )
  })

  it('never cuts a long filled job, like the digest file', () => {
    const template = '{requirements}'.repeat(40)
    const message = toSampleMessage(template)

    expect(countChars(message)).toBeGreaterThan(MAX_MESSAGE_CHARS)
    expect(message.endsWith('…')).toBe(false)
  })

  it('is empty for an empty template', () => {
    expect(toSampleMessage('')).toBe('')
  })
})
