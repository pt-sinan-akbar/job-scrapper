import { computed, ref, toRaw, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  findSiteIssue,
  hasConfigChanges,
  isSame,
  readSiteToggle,
  setSiteToggle,
  toConfigChanges,
  toSiteToggleChanges,
  toSiteIssues,
  type ConfigChanges,
  type ConfigSnapshot,
  type ConfigValues,
  type SiteIssue,
  type SiteSetting,
  type SiteToggle,
} from '@/modules/config/domain/entities/ScraperConfig'
import { requireConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

function toCurrentIssue(values: ConfigValues, issue: SiteIssue): SiteIssue | null {
  const site = values.sites.find((candidate) => candidate.name === issue.siteName)
  const issues = site === undefined ? [] : toSiteIssues(site)
  return issues.find((candidate) => candidate.field === issue.field) ?? null
}

export const useConfigStore = defineStore('config', () => {
  const status = ref<LoadStatus>('idle')
  const values = ref<ConfigValues | null>(null)
  const snapshot = ref<ConfigSnapshot | null>(null)
  const errorMessage = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const isSaving = ref(false)
  const siteIssue = ref<SiteIssue | null>(null)
  const autoSaveError = ref<string | null>(null)
  let autoSaveQueue: Promise<boolean> = Promise.resolve(true)

  const isDirty = computed(
    () =>
      values.value !== null &&
      snapshot.value !== null &&
      !isSame(values.value, snapshot.value.values),
  )

  function setSiteIssue(issue: SiteIssue | null): void {
    siteIssue.value = issue
    saveError.value = issue?.message ?? null
  }

  watch(
    values,
    (next) => {
      const issue = siteIssue.value
      if (issue === null || next === null) {
        return
      }
      const current = toCurrentIssue(next, issue)
      if (current?.message !== issue.message) {
        setSiteIssue(current)
      }
    },
    { deep: true },
  )

  function discard(): void {
    if (snapshot.value === null) {
      return
    }
    values.value = structuredClone(toRaw(snapshot.value.values))
    setSiteIssue(null)
  }

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const next = await requireConfigUseCases().getConfig.execute()
      snapshot.value = next
      values.value = structuredClone(next.values)
      status.value = 'ready'
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      status.value = 'error'
    }
  }

  async function save(): Promise<boolean> {
    const current = values.value
    const loaded = snapshot.value
    if (current === null || loaded === null || loaded.isStale) {
      return false
    }
    const issue = findSiteIssue(current)
    if (issue !== undefined) {
      setSiteIssue(issue)
      return false
    }
    siteIssue.value = null
    const changes = toConfigChanges(current, loaded.values)
    if (!hasConfigChanges(changes)) {
      return true
    }
    isSaving.value = true
    saveError.value = null
    try {
      await requireConfigUseCases().saveConfig.execute(changes, loaded.version)
      await load()
      return true
    } catch (error) {
      saveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isSaving.value = false
    }
  }

  function saveJobFields(fields: string[]): Promise<boolean> {
    const current = values.value
    if (current === null) {
      return Promise.resolve(false)
    }
    current.fields = fields
    return queueAutoSave({ fields }, revertJobFields)
  }

  function saveSiteToggle(toggle: SiteToggle): Promise<boolean> {
    const current = values.value
    const savedSite = findSavedSite(toggle.siteName)
    if (current === null || savedSite === undefined) {
      return Promise.resolve(false)
    }
    current.sites = current.sites.map((site) =>
      site.name === toggle.siteName ? setSiteToggle(site, toggle.field, toggle.isOn) : site,
    )
    return queueAutoSave(toSiteToggleChanges(savedSite, toggle), () => revertSiteToggle(toggle))
  }

  function queueAutoSave(changes: ConfigChanges, revert: () => void): Promise<boolean> {
    autoSaveQueue = autoSaveQueue.then(() => sendAutoSave(changes, revert))
    return autoSaveQueue
  }

  async function sendAutoSave(changes: ConfigChanges, revert: () => void): Promise<boolean> {
    const loaded = snapshot.value
    if (loaded === null || loaded.isStale) {
      revert()
      return false
    }
    autoSaveError.value = null
    try {
      await requireConfigUseCases().saveConfig.execute(changes, loaded.version)
      await refreshSnapshotKeepingEdits()
      return true
    } catch (error) {
      revert()
      autoSaveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    }
  }

  async function refreshSnapshotKeepingEdits(): Promise<void> {
    const next = await requireConfigUseCases().getConfig.execute()
    snapshot.value = next
    if (values.value === null || isSame(values.value, next.values)) {
      values.value = structuredClone(next.values)
    }
  }

  function revertJobFields(): void {
    const loaded = snapshot.value
    if (values.value === null || loaded === null) {
      return
    }
    values.value.fields = [...loaded.values.fields]
  }

  function revertSiteToggle(toggle: SiteToggle): void {
    const savedSite = findSavedSite(toggle.siteName)
    if (values.value === null || savedSite === undefined) {
      return
    }
    const savedIsOn = readSiteToggle(savedSite, toggle.field)
    values.value.sites = values.value.sites.map((site) =>
      site.name === toggle.siteName ? setSiteToggle(site, toggle.field, savedIsOn) : site,
    )
  }

  function findSavedSite(siteName: string): SiteSetting | undefined {
    return snapshot.value?.values.sites.find((site) => site.name === siteName)
  }

  return {
    status,
    values,
    snapshot,
    errorMessage,
    saveError,
    siteIssue,
    isSaving,
    isDirty,
    autoSaveError,
    discard,
    load,
    save,
    saveJobFields,
    saveSiteToggle,
  }
})
