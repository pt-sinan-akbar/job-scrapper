export const MAX_MESSAGE_CHARS = 2000
export const EMPTY_VALUE_TEXT = '-'

const PLACEHOLDER_PATTERN = /\{([A-Za-z_][\p{L}\p{N}_]*)\}/gu

export type DiscordJobText = string | number | null

export type DiscordJob = Readonly<Record<string, DiscordJobText>>

export const SAMPLE_JOB: DiscordJob = {
  site: 'jobstreet',
  matched_keyword: 'full stack engineer',
  title: 'IoT Solution Engineer (Fullstack IoT)',
  company: 'PT Onesia Nusantara Evolusioner',
  company_id: 'sample-company-000',
  url: 'https://id.jobstreet.com/id/job/00000000',
  location: 'West Jakarta, Jakarta',
  salary: 'Rp7.000.000 – Rp8.000.000 per month',
  salary_min: 7000000,
  salary_max: 8000000,
  posted_date: '2026-11-19T02:00:00+00:00',
  posted_at: '2026-11-19T02:00:00+00:00',
  work_type: 'on-site',
  employment_type: 'contract/temp',
  experience_level: '1-3 years',
  job_id: '00000000',
  requirements: [
    '- Bachelor degree in Computer Science, Electrical Engineering or a related field',
    '- At least 2 years of experience building full stack web applications',
    '- Hands-on experience with IoT protocols such as MQTT and HTTP',
    '- Comfortable with Node.js, a modern frontend framework and SQL databases',
    '- Willing to work on-site in West Jakarta',
  ].join('\n'),
}

export interface DiscordSettings {
  isConfigured: boolean
  tokenHint: string | null
  defaultChannelId: string | null
  mentionUserId: string | null
  messageTemplate: string
  maxChars: number
  updatedAt: string | null
}

export interface DiscordSettingsForm {
  token: string
  defaultChannelId: string
  mentionUserId: string
  messageTemplate: string
  maxChars: string
}

export interface DiscordSettingsChanges {
  token?: string
  defaultChannelId?: string | null
  mentionUserId?: string | null
  messageTemplate?: string
  maxChars?: number
}

export interface DiscordBot {
  name: string
  id: string
}

export interface DiscordChannel {
  id: string
  name: string
  guildId: string
  guildName: string
}

export interface DiscordContent {
  text: string
}

export type DiscordMessageKind = 'text' | 'file'

export interface DiscordMessageResult {
  index: number
  kind: DiscordMessageKind
  title: string | null
  jobCount: number
  status: 'sent' | 'failed'
  messageId: string | null
  error: string | null
}

export interface DiscordSendResult {
  sent: number
  failed: number
  results: DiscordMessageResult[]
}

export function toSettingsForm(settings: DiscordSettings): DiscordSettingsForm {
  return {
    token: '',
    defaultChannelId: settings.defaultChannelId ?? '',
    mentionUserId: settings.mentionUserId ?? '',
    messageTemplate: settings.messageTemplate,
    maxChars: String(settings.maxChars),
  }
}

function toNullableId(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

export function toSettingsChanges(
  form: DiscordSettingsForm,
  settings: DiscordSettings,
): DiscordSettingsChanges {
  const token = form.token.trim()
  const defaultChannelId = toNullableId(form.defaultChannelId)
  const mentionUserId = toNullableId(form.mentionUserId)
  const maxChars = Number(form.maxChars)
  return {
    ...(token === '' ? {} : { token }),
    ...(defaultChannelId === settings.defaultChannelId ? {} : { defaultChannelId }),
    ...(mentionUserId === settings.mentionUserId ? {} : { mentionUserId }),
    ...(form.messageTemplate === settings.messageTemplate
      ? {}
      : { messageTemplate: form.messageTemplate }),
    ...(maxChars === settings.maxChars ? {} : { maxChars }),
  }
}

export function toMentionPrefix(userId: string | null, isMentioned: boolean): string {
  return isMentioned && userId !== null ? `<@${userId}>\n` : ''
}

export function countChars(text: string): number {
  return [...text].length
}

function pluralMessages(count: number): string {
  return count === 1 ? '1 message' : `${count} messages`
}

export function toSendSummary(result: DiscordSendResult): string {
  if (result.failed === 0) {
    return `Sent ${pluralMessages(result.sent)}`
  }
  if (result.sent === 0) {
    return `Nothing was sent, ${result.failed} failed`
  }
  return `Sent ${result.sent}, ${result.failed} failed`
}

export function hasSettingsChanges(form: DiscordSettingsForm, settings: DiscordSettings): boolean {
  return Object.keys(toSettingsChanges(form, settings)).length > 0
}

export function fillTemplate(template: string, job: DiscordJob): string {
  return template.replace(PLACEHOLDER_PATTERN, (_placeholder: string, fieldName: string) =>
    toJobText(job, fieldName),
  )
}

export function toSampleMessage(template: string): string {
  return fillTemplate(template, SAMPLE_JOB)
}

function toJobText(job: DiscordJob, fieldName: string): string {
  if (!Object.keys(job).includes(fieldName)) {
    return EMPTY_VALUE_TEXT
  }
  const jobValue = job[fieldName]
  if (jobValue === null || jobValue === undefined) {
    return EMPTY_VALUE_TEXT
  }
  const jobText = String(jobValue)
  if (jobText.trim() === '') {
    return EMPTY_VALUE_TEXT
  }
  return jobText
}
