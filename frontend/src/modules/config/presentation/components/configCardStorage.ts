import {
  browserStorage,
  OFF_VALUE,
  readStorageItem,
  writeStorageFlag,
  type KeyValueStorage,
} from '@/shared/utils/browserStorage'

export type ConfigCardStorage = KeyValueStorage

export const CONFIG_CARD_STORAGE_KEY = 'scraper-ui:runs:config-card-open'

export function readConfigCardOpen(getStorage: () => ConfigCardStorage = browserStorage): boolean {
  return readStorageItem(CONFIG_CARD_STORAGE_KEY, getStorage) !== OFF_VALUE
}

export function writeConfigCardOpen(
  isOpen: boolean,
  getStorage: () => ConfigCardStorage = browserStorage,
): void {
  writeStorageFlag(CONFIG_CARD_STORAGE_KEY, isOpen, getStorage)
}
