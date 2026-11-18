import { describe, expect, it } from 'vitest'
import {
  CONFIG_CARD_STORAGE_KEY,
  readConfigCardOpen,
  writeConfigCardOpen,
  type ConfigCardStorage,
} from '@/modules/config/presentation/components/configCardStorage'

function memoryStorage(initial: Record<string, string> = {}) {
  const values = { ...initial }
  const storage: ConfigCardStorage = {
    getItem: (key) => values[key] ?? null,
    setItem: (key, value) => {
      values[key] = value
    },
  }
  return { values, storage }
}

const throwingStorage: ConfigCardStorage = {
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('config card storage', () => {
  it('starts open when nothing is stored', () => {
    expect(readConfigCardOpen(() => memoryStorage().storage)).toBe(true)
  })

  it('reads back open', () => {
    const { storage } = memoryStorage({ [CONFIG_CARD_STORAGE_KEY]: 'true' })

    expect(readConfigCardOpen(() => storage)).toBe(true)
  })

  it('reads back closed', () => {
    const { storage } = memoryStorage({ [CONFIG_CARD_STORAGE_KEY]: 'false' })

    expect(readConfigCardOpen(() => storage)).toBe(false)
  })

  it('falls back to open for an unknown stored value', () => {
    const { storage } = memoryStorage({ [CONFIG_CARD_STORAGE_KEY]: 'yes' })

    expect(readConfigCardOpen(() => storage)).toBe(true)
  })

  it('falls back to open when reading throws', () => {
    expect(readConfigCardOpen(() => throwingStorage)).toBe(true)
  })

  it('falls back to open when the storage itself cannot be reached', () => {
    expect(
      readConfigCardOpen(() => {
        throw new Error('no storage')
      }),
    ).toBe(true)
  })

  it('writes the open state', () => {
    const { values, storage } = memoryStorage()

    writeConfigCardOpen(true, () => storage)

    expect(values[CONFIG_CARD_STORAGE_KEY]).toBe('true')
  })

  it('does not throw when writing is blocked', () => {
    expect(() => writeConfigCardOpen(true, () => throwingStorage)).not.toThrow()
  })

  it('does not throw when the storage itself cannot be reached', () => {
    expect(() =>
      writeConfigCardOpen(true, () => {
        throw new Error('no storage')
      }),
    ).not.toThrow()
  })
})
