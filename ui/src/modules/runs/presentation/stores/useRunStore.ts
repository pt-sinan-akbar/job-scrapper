import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError } from '@/core/errors/ApiError'
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import { requireRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

export const POLL_INTERVAL_MS = 2000
export const MAX_POLL_FAILURES = 5
export const MAX_DISCORD_WAIT_POLLS = 3
const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'
const LOST_RUN_MESSAGE = 'Lost track of this run. Reload the page to check it.'

export interface RunError {
  readonly message: string
}

const NOT_FOUND_STATUS = 404

function isBusy(record: RunRecord): boolean {
  return record.status === 'running' || record.discordStatus === 'sending'
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === NOT_FOUND_STATUS
}

export const useRunStore = defineStore('runs', () => {
  const status = ref<LoadStatus>('idle')
  const options = ref<RunOptions | null>(null)
  const activeRunId = ref<string | null>(null)
  const runOutcome = ref<RunRecord | null>(null)
  const discordOutcome = ref<RunRecord | null>(null)
  const errorMessage = ref<string | null>(null)
  const runError = ref<RunError | null>(null)
  const latestRun = ref<RunDetail | null>(null)
  const latestStatus = ref<LoadStatus>('idle')
  const latestErrorMessage = ref<string | null>(null)
  const lostRunId = ref<string | null>(null)
  const goneRunId = ref<string | null>(null)
  let latestVersion = 0
  let pollFailures = 0
  let discordWaitPolls = 0
  let runEndReportedFor: string | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let session = 0
  const expectedDiscordIds = new Set<string>()

  const isRunning = computed(() => activeRunId.value !== null)

  const isResultsLost = computed(() => lostRunId.value !== null)

  const isResultsPending = computed(() => {
    if (isResultsLost.value) {
      return false
    }
    const shown = latestRun.value
    if (isRunning.value && shown?.record.id !== activeRunId.value) {
      return true
    }
    if (shown === null) {
      return latestStatus.value === 'loading'
    }
    return shown.record.status === 'running' && shown.record.id !== goneRunId.value
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

  function followRun(id: string): void {
    activeRunId.value = id
    lostRunId.value = null
    pollFailures = 0
    discordWaitPolls = 0
    schedulePoll(id)
  }

  function stopFollowing(id: string): void {
    clearPollTimer()
    activeRunId.value = null
    expectedDiscordIds.delete(id)
  }

  function isFollowing(id: string, startedIn: number): boolean {
    return session === startedIn && activeRunId.value === id
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
    runError.value = { message: LOST_RUN_MESSAGE }
    lostRunId.value = id
    stopFollowing(id)
  }

  function handleRunGone(id: string): void {
    if (latestRun.value?.record.id !== id) {
      markLost(id)
      return
    }
    goneRunId.value = id
    stopFollowing(id)
  }

  function followIfBusy(detail: RunDetail | null): void {
    if (detail === null || !isBusy(detail.record) || activeRunId.value !== null) {
      return
    }
    if (detail.record.discordStatus === 'sending') {
      expectedDiscordIds.add(detail.record.id)
    }
    followRun(detail.record.id)
  }

  function applyLatest(next: RunDetail | null): void {
    latestRun.value = next
    if (next !== null && next.record.id === lostRunId.value) {
      lostRunId.value = null
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
      const next = await requireRunUseCases().getOptions.execute()
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
      const next = await requireRunUseCases().getLatestRun.execute()
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

  function showDetail(detail: RunDetail): void {
    latestVersion += 1
    latestRun.value = detail
  }

  function shouldWaitForDiscord(record: RunRecord): boolean {
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
    let detail: RunDetail
    try {
      detail = await requireRunUseCases().getRun.execute(id)
    } catch (error) {
      if (!isFollowing(id, startedIn)) {
        return
      }
      if (isNotFound(error)) {
        handleRunGone(id)
      } else {
        handlePollFailure(id)
      }
      return
    }
    if (isFollowing(id, startedIn)) {
      handleDetail(detail)
    }
  }

  function handleDetail(detail: RunDetail): void {
    const { record } = detail
    pollFailures = 0
    if (record.discordStatus === 'sending') {
      expectedDiscordIds.add(record.id)
    }
    if (record.status !== 'running') {
      recordRunEnd(record)
      showDetail(detail)
    }
    if (isBusy(record) || shouldWaitForDiscord(record)) {
      schedulePoll(record.id)
      return
    }
    recordDiscordOutcome(record)
    stopFollowing(record.id)
  }

  function recordRunEnd(record: RunRecord): void {
    if (runEndReportedFor !== record.id) {
      runEndReportedFor = record.id
      runOutcome.value = record
    }
  }

  function recordDiscordOutcome(record: RunRecord): void {
    if (record.discordStatus !== null && expectedDiscordIds.has(record.id)) {
      discordOutcome.value = record
    }
  }

  async function start(keywords: string[], sites: string[], notifyDiscord: boolean): Promise<void> {
    if (isRunning.value) {
      return
    }
    const startedIn = session
    runError.value = null
    try {
      const record = await requireRunUseCases().startRun.execute(keywords, sites, notifyDiscord)
      if (startedIn !== session) {
        return
      }
      if (notifyDiscord) {
        expectedDiscordIds.add(record.id)
      }
      followRun(record.id)
    } catch (error) {
      if (startedIn === session) {
        runError.value = { message: toErrorMessage(error, FALLBACK_ERROR_MESSAGE) }
      }
    }
  }

  function reset(): void {
    session += 1
    clearPollTimer()
    expectedDiscordIds.clear()
    pollFailures = 0
    discordWaitPolls = 0
    runEndReportedFor = null
    status.value = 'idle'
    options.value = null
    activeRunId.value = null
    runOutcome.value = null
    discordOutcome.value = null
    errorMessage.value = null
    runError.value = null
    latestRun.value = null
    latestStatus.value = 'idle'
    latestErrorMessage.value = null
    lostRunId.value = null
    goneRunId.value = null
  }

  return {
    status,
    options,
    errorMessage,
    runError,
    runOutcome,
    discordOutcome,
    latestRun,
    latestStatus,
    latestErrorMessage,
    isRunning,
    isResultsPending,
    isResultsLost,
    load,
    loadLatest,
    start,
    reset,
  }
})
