const UNSAFE_ID_CHARS = /[^a-z0-9_-]+/g
const EDGE_DASHES = /^-+|-+$/g
const FALLBACK_ID_PREFIX = 'site'

export function toSiteIdPrefix(siteName: string): string {
  const prefix = siteName.toLowerCase().replace(UNSAFE_ID_CHARS, '-').replace(EDGE_DASHES, '')
  return prefix === '' ? FALLBACK_ID_PREFIX : prefix
}
