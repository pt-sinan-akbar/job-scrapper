import { describe, expect, it } from 'vitest'
import {
  isResultsTab,
  readResultsTab,
  RESULTS_TAB_STORAGE_KEY,
  RESULTS_TABS,
  writeResultsTab,
  type ResultsTabStorage,
} from '@/modules/runs/presentation/components/resultsTabStorage'

function memoryStorage(initial: Record<string, string> = {}) {
  const values = { ...initial }
  const storage: ResultsTabStorage = {
    getItem: (key) => values[key] ?? null,
    setItem: (key, value) => {
      values[key] = value
    },
  }
  return { values, storage }
}

const throwingStorage: ResultsTabStorage = {
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('results tab storage', () => {
  it('starts on jobs when nothing is stored', () => {
    expect(readResultsTab(() => memoryStorage().storage)).toBe('jobs')
  })

  it.each(RESULTS_TABS)('reads back %s', (tab) => {
    const { storage } = memoryStorage({ [RESULTS_TAB_STORAGE_KEY]: tab })

    expect(readResultsTab(() => storage)).toBe(tab)
  })

  it('falls back to jobs for an unknown stored value', () => {
    const { storage } = memoryStorage({ [RESULTS_TAB_STORAGE_KEY]: 'xml' })

    expect(readResultsTab(() => storage)).toBe('jobs')
  })

  it('falls back to jobs when reading throws', () => {
    expect(readResultsTab(() => throwingStorage)).toBe('jobs')
  })

  it('falls back to jobs when the storage itself cannot be reached', () => {
    expect(
      readResultsTab(() => {
        throw new Error('no storage')
      }),
    ).toBe('jobs')
  })

  it('writes the tab', () => {
    const { values, storage } = memoryStorage()

    writeResultsTab('json', () => storage)

    expect(values[RESULTS_TAB_STORAGE_KEY]).toBe('json')
  })

  it('does not throw when writing is blocked', () => {
    expect(() => writeResultsTab('json', () => throwingStorage)).not.toThrow()
  })

  it('does not throw when the storage itself cannot be reached', () => {
    expect(() =>
      writeResultsTab('json', () => {
        throw new Error('no storage')
      }),
    ).not.toThrow()
  })

  it('knows every tab id and nothing else', () => {
    expect(RESULTS_TABS.every((tab) => isResultsTab(tab))).toBe(true)
    expect(RESULTS_TABS).toEqual(['jobs', 'json'])
    expect(['xml', '', null, 3].some((value) => isResultsTab(value))).toBe(false)
  })
})
