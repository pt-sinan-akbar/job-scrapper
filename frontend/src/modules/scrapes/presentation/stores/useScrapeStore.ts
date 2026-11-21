import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError } from '@/core/errors/ApiError'
import type {
  ScrapeDetail,
  ScrapeOptions,
  ScrapeRecord,
} from '@/modules/scrapes/domain/entities/Scrape'
import { requireScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

export const POLL_INTERVAL_MS = 2000
export const MAX_POLL_FAILURES = 5
export const MAX_DISCORD_WAIT_POLLS = 3
const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'
const LOST_SCRAPE_MESSAGE = 'Lost track of this run. Reload the page to check it.'

export interface ScrapeError {
  readonly message: string
}

const NOT_FOUND_STATUS = 404

function isBusy(record: ScrapeRecord): boolean {
  return record.status === 'running' || record.discordStatus === 'sending'
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === NOT_FOUND_STATUS
}

export const useScrapeStore = defineStore('scrapes', () => {
  const status = ref<LoadStatus>('idle')
  const options = ref<ScrapeOptions | null>(null)
  const activeScrapeId = ref<string | null>(null)
  const scrapeOutcome = ref<ScrapeRecord | null>(null)
  const discordOutcome = ref<ScrapeRecord | null>(null)
  const errorMessage = ref<string | null>(null)
  const scrapeError = ref<ScrapeError | null>(null)
  const latestScrape = ref<ScrapeDetail | null>(null)
  const latestStatus = ref<LoadStatus>('idle')
  const latestErrorMessage = ref<string | null>(null)
  const lostScrapeId = ref<string | null>(null)
  const goneScrapeId = ref<string | null>(null)
  const latestSendScrapeId = ref<string | null>(null)
  const latestSendError = ref<string | null>(null)
  const isRequestingLatestSend = ref(false)
  let latestSendVersion = 0
  let latestVersion = 0
  let pollFailures = 0
  let discordWaitPolls = 0
  let scrapeEndReportedFor: string | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let session = 0
  const expectedDiscordIds = new Set<string>()

  const isScraping = computed(() => activeScrapeId.value !== null)

  const isResultsLost = computed(() => lostScrapeId.value !== null)

  const isSendingLatest = computed(() => {
    if (isRequestingLatestSend.value) {
      return true
    }
    return latestSendScrapeId.value !== null && activeScrapeId.value === latestSendScrapeId.value
  })

  const latestSendOutcome = computed(() => {
    const record = latestScrape.value?.record
    if (record === undefined || record.id !== latestSendScrapeId.value) {
      return null
    }
    if (record.discordStatus === null || record.discordStatus === 'sending') {
      return null
    }
    return record
  })

  const isResultsPending = computed(() => {
    if (isResultsLost.value) {
      return false
    }
    const shown = latestScrape.value
    if (isScraping.value && shown?.record.id !== activeScrapeId.value) {
      return true
    }
    if (shown === null) {
      return latestStatus.value === 'loading'
    }
    return shown.record.status === 'running' && shown.record.id !== goneScrapeId.value
  })

  function clearPollTimer(): void {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function schedulePoll(id: string): void {
    clearPollTimer()
    pollTimer = setTimeout(() => {
      pollTimer = null
      void poll(id)
    }, POLL_INTERVAL_MS)
  }

  function followScrape(id: string): void {
    activeScrapeId.value = id
    lostScrapeId.value = null
    pollFailures = 0
    discordWaitPolls = 0
    schedulePoll(id)
  }

  function stopFollowing(id: string): void {
    clearPollTimer()
    activeScrapeId.value = null
    expectedDiscordIds.delete(id)
  }

  function isFollowing(id: string, startedIn: number): boolean {
    return session === startedIn && activeScrapeId.value === id
  }

  function handlePollFailure(id: string): void {
    pollFailures += 1
    if (pollFailures < MAX_POLL_FAILURES) {
      schedulePoll(id)
      return
    }
    markLost(id)
  }

  function markLost(id: string): void {
    scrapeError.value = { message: LOST_SCRAPE_MESSAGE }
    lostScrapeId.value = id
    stopFollowing(id)
  }

  function handleScrapeGone(id: string): void {
    if (latestScrape.value?.record.id !== id) {
      markLost(id)
      return
    }
    goneScrapeId.value = id
    stopFollowing(id)
  }

  function followIfBusy(detail: ScrapeDetail | null): void {
    if (detail === null || !isBusy(detail.record) || activeScrapeId.value !== null) {
      return
    }
    if (detail.record.discordStatus === 'sending') {
      expectedDiscordIds.add(detail.record.id)
    }
    followScrape(detail.record.id)
  }

  function applyLatest(next: ScrapeDetail | null): void {
    latestScrape.value = next
    if (next !== null && next.record.id === lostScrapeId.value) {
      lostScrapeId.value = null
    }
    followIfBusy(next)
  }

  async function load(): Promise<void> {
    if (status.value === 'loading') {
      return
    }
    const startedIn = session
    status.value = 'loading'
    errorMessage.value = null
    try {
      const next = await requireScrapeUseCases().getOptions.execute()
      if (startedIn === session) {
        options.value = next
        status.value = 'ready'
      }
    } catch (error) {
      if (startedIn === session) {
        errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
        status.value = 'error'
      }
    }
  }

  async function loadLatest(): Promise<void> {
    if (latestStatus.value === 'loading') {
      return
    }
    const startedIn = session
    const versionAtStart = latestVersion
    latestStatus.value = 'loading'
    latestErrorMessage.value = null
    try {
      const next = await requireScrapeUseCases().getLatestScrape.execute()
      if (startedIn !== session) {
        return
      }
      if (versionAtStart === latestVersion) {
        applyLatest(next)
      }
      latestStatus.value = 'ready'
    } catch (error) {
      if (startedIn === session) {
        latestErrorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
        latestStatus.value = 'error'
      }
    }
  }

  function showDetail(detail: ScrapeDetail): void {
    latestVersion += 1
    latestScrape.value = detail
  }

  function shouldWaitForDiscord(record: ScrapeRecord): boolean {
    const isAwaiting =
      expectedDiscordIds.has(record.id) &&
      record.status !== 'running' &&
      record.discordStatus === null
    if (!isAwaiting || discordWaitPolls >= MAX_DISCORD_WAIT_POLLS) {
      return false
    }
    discordWaitPolls += 1
    return true
  }

  async function poll(id: string): Promise<void> {
    const startedIn = session
    let detail: ScrapeDetail
    try {
      detail = await requireScrapeUseCases().getScrape.execute(id)
    } catch (error) {
      if (!isFollowing(id, startedIn)) {
        return
      }
      if (isNotFound(error)) {
        handleScrapeGone(id)
      } else {
        handlePollFailure(id)
      }
      return
    }
    if (isFollowing(id, startedIn)) {
      handleDetail(detail)
    }
  }

  function handleDetail(detail: ScrapeDetail): void {
    const { record } = detail
    pollFailures = 0
    if (record.discordStatus === 'sending') {
      expectedDiscordIds.add(record.id)
    }
    if (record.status !== 'running') {
      recordScrapeEnd(record)
      showDetail(detail)
    }
    if (isBusy(record) || shouldWaitForDiscord(record)) {
      schedulePoll(record.id)
      return
    }
    recordDiscordOutcome(record)
    stopFollowing(record.id)
  }

  function recordScrapeEnd(record: ScrapeRecord): void {
    if (scrapeEndReportedFor !== record.id) {
      scrapeEndReportedFor = record.id
      scrapeOutcome.value = record
    }
  }

  function recordDiscordOutcome(record: ScrapeRecord): void {
    if (record.id === latestSendScrapeId.value) {
      return
    }
    if (record.discordStatus !== null && expectedDiscordIds.has(record.id)) {
      discordOutcome.value = record
    }
  }

  async function start(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<void> {
    if (isScraping.value) {
      return
    }
    const startedIn = session
    scrapeError.value = null
    try {
      const record = await requireScrapeUseCases().startScrape.execute(
        keywords,
        sites,
        notifyDiscord,
      )
      if (startedIn !== session) {
        return
      }
      if (notifyDiscord) {
        expectedDiscordIds.add(record.id)
      }
      followScrape(record.id)
    } catch (error) {
      if (startedIn === session) {
        scrapeError.value = { message: toErrorMessage(error, FALLBACK_ERROR_MESSAGE) }
      }
    }
  }

  async function sendLatestToDiscord(): Promise<void> {
    if (isScraping.value || isRequestingLatestSend.value) {
      return
    }
    const startedIn = session
    latestSendVersion += 1
    const requestedAs = latestSendVersion
    isRequestingLatestSend.value = true
    latestSendError.value = null
    latestSendScrapeId.value = null
    try {
      const record = await requireScrapeUseCases().sendLatestScrapeToDiscord.execute()
      if (isLatestSendCurrent(startedIn, requestedAs)) {
        followLatestSend(record)
      }
    } catch (error) {
      if (isLatestSendCurrent(startedIn, requestedAs)) {
        latestSendError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      }
    } finally {
      if (isLatestSendCurrent(startedIn, requestedAs)) {
        isRequestingLatestSend.value = false
      }
    }
  }

  function stopLatestSend(): void {
    const followedId = latestSendScrapeId.value
    latestSendVersion += 1
    isRequestingLatestSend.value = false
    latestSendScrapeId.value = null
    latestSendError.value = null
    if (followedId !== null && activeScrapeId.value === followedId) {
      stopFollowing(followedId)
    }
  }

  function isLatestSendCurrent(startedIn: number, requestedAs: number): boolean {
    return session === startedIn && latestSendVersion === requestedAs
  }

  function followLatestSend(record: ScrapeRecord): void {
    latestSendScrapeId.value = record.id
    scrapeEndReportedFor = record.id
    showRecord(record)
    followScrape(record.id)
  }

  function showRecord(record: ScrapeRecord): void {
    const shown = latestScrape.value
    if (shown !== null && shown.record.id === record.id) {
      showDetail({ ...shown, record })
    }
  }

  function reset(): void {
    session += 1
    clearPollTimer()
    expectedDiscordIds.clear()
    pollFailures = 0
    discordWaitPolls = 0
    scrapeEndReportedFor = null
    status.value = 'idle'
    options.value = null
    activeScrapeId.value = null
    scrapeOutcome.value = null
    discordOutcome.value = null
    errorMessage.value = null
    scrapeError.value = null
    latestScrape.value = null
    latestStatus.value = 'idle'
    latestErrorMessage.value = null
    lostScrapeId.value = null
    goneScrapeId.value = null
    latestSendScrapeId.value = null
    latestSendError.value = null
    isRequestingLatestSend.value = false
  }

  return {
    status,
    options,
    errorMessage,
    scrapeError,
    scrapeOutcome,
    discordOutcome,
    latestScrape,
    latestStatus,
    latestErrorMessage,
    isScraping,
    isResultsPending,
    isResultsLost,
    isSendingLatest,
    latestSendOutcome,
    latestSendError,
    load,
    loadLatest,
    start,
    sendLatestToDiscord,
    stopLatestSend,
    reset,
  }
})
