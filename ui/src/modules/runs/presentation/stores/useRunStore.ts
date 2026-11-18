import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
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

function isBusy(record: RunRecord): boolean {
  return record.status === 'running' || record.discordStatus === 'sending'
}

export const useRunStore = defineStore('runs', () => {
  const status = ref<LoadStatus>('idle')
  const options = ref<RunOptions | null>(null)
  const activeRunId = ref<string | null>(null)
  const runOutcome = ref<RunRecord | null>(null)
  const discordOutcome = ref<RunRecord | null>(null)
  const errorMessage = ref<string | null>(null)
  const runError = ref<RunError | null>(null)
  let pollFailures = 0
  let discordWaitPolls = 0
  let runEndReportedFor: string | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let session = 0
  const expectedDiscordIds = new Set<string>()

  const isRunning = computed(() => activeRunId.value !== null)

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
    runError.value = { message: LOST_RUN_MESSAGE }
    stopFollowing(id)
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
    let record: RunRecord
    try {
      record = await requireRunUseCases().getRun.execute(id)
    } catch {
      if (isFollowing(id, startedIn)) {
        handlePollFailure(id)
      }
      return
    }
    if (isFollowing(id, startedIn)) {
      handleRecord(record)
    }
  }

  function handleRecord(record: RunRecord): void {
    pollFailures = 0
    if (record.discordStatus === 'sending') {
      expectedDiscordIds.add(record.id)
    }
    if (record.status !== 'running') {
      recordRunEnd(record)
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
  }

  return {
    status,
    options,
    errorMessage,
    runError,
    runOutcome,
    discordOutcome,
    isRunning,
    load,
    start,
    reset,
  }
})
