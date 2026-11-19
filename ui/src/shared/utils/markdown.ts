const ALLOWED_TAGS = [
  'p',
  'br',
  'ul',
  'ol',
  'li',
  'strong',
  'em',
  'b',
  'i',
  's',
  'del',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'a',
  'code',
  'pre',
  'blockquote',
]
const ALLOWED_ATTR = ['href', 'target', 'rel']
const ALLOWED_URI_REGEXP = /^(?:https?|mailto):/i
const LINK_TARGET = '_blank'
const LINK_REL = 'noopener noreferrer'

const INLINE_HTML_TAGS: ReadonlySet<string> = new Set([
  'a',
  'abbr',
  'b',
  'code',
  'del',
  'em',
  'i',
  'ins',
  'mark',
  's',
  'small',
  'span',
  'strong',
  'sub',
  'sup',
  'u',
])

const MAX_PLAIN_TEXT_SOURCE_CHARS = 20_000
const LINE_BREAKS = /\r\n?/g
const FENCE_LINES = /^[ \t]*(?:`{3,}|~{3,}).*$/gm
const HTML_COMMENTS = /<!--[\s\S]{0,5000}?-->/g
const AUTOLINKS = /<((?:https?:\/\/|mailto:)[^\s<>]{1,2000})>/g
const HTML_TAGS = /<\/?([a-zA-Z][a-zA-Z0-9]{0,30})(?:\s[^<>]{0,2000})?\/?>/g
const INLINE_LINKS = /!?\[([^\]\n]{0,1000})\]\([^)\n]{0,2000}\)/g
const REFERENCE_LINKS = /!?\[([^\]\n]{1,1000})\]\[[^\]\n]{0,200}\]/g
const REFERENCE_DEFINITIONS = /^[ \t]*\[[^\]\n]{1,200}\]:[ \t]+\S.*$/gm
const HEADING_MARKS = /^[ \t]*#{1,6}[ \t]+/gm
const HEADING_CLOSERS = /[ \t]{1,20}#{1,20}[ \t]{0,20}$/gm
const RULE_LINES = /^[ \t]*(?:=+|(?:[-*_][ \t]*){3,})[ \t]*$/gm
const QUOTE_MARKS = /^[ \t]*(?:>[ \t]?)+/gm
const LIST_MARKS = /^[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+/gm
const STRONG_STARS = /(?<!\\)\*\*(?=\S)(.{1,1000}?)(?<=\S)\*\*/g
const STRONG_BARS = /(?<![\\\w])__(?=\S)(.{1,1000}?)(?<=\S)__(?!\w)/g
const EMPHASIS_STARS = /(?<!\\)\*(?=\S)(.{1,1000}?)(?<=\S)(?<!\\)\*/g
const EMPHASIS_BARS = /(?<![\\\w])_(?=\S)(.{1,1000}?)(?<=\S)_(?!\w)/g
const STRIKES = /~~(?=\S)(.{1,1000}?)(?<=\S)~~/g
const INLINE_CODE = /(`+)(.{1,1000}?)\1/g
const ESCAPES = /\\([\\`*_{}[\]()#+\-.!>~|<])/g
const WHITESPACE = /\s+/g

type TextTransform = (text: string) => string

let rendererPromise: Promise<TextTransform> | null = null

function stripHtmlTag(_tag: string, name: string): string {
  return INLINE_HTML_TAGS.has(name.toLowerCase()) ? '' : ' '
}

export function markdownToPlainText(markdown: string): string {
  return markdown
    .slice(0, MAX_PLAIN_TEXT_SOURCE_CHARS)
    .replace(LINE_BREAKS, '\n')
    .replace(FENCE_LINES, '')
    .replace(HTML_COMMENTS, '')
    .replace(AUTOLINKS, '$1')
    .replace(HTML_TAGS, stripHtmlTag)
    .replace(INLINE_LINKS, '$1')
    .replace(REFERENCE_LINKS, '$1')
    .replace(REFERENCE_DEFINITIONS, '')
    .replace(HEADING_MARKS, '')
    .replace(HEADING_CLOSERS, '')
    .replace(RULE_LINES, '')
    .replace(QUOTE_MARKS, '')
    .replace(LIST_MARKS, '')
    .replace(STRONG_STARS, '$1')
    .replace(STRONG_BARS, '$1')
    .replace(EMPHASIS_STARS, '$1')
    .replace(EMPHASIS_BARS, '$1')
    .replace(STRIKES, '$1')
    .replace(INLINE_CODE, '$2')
    .replace(ESCAPES, '$1')
    .replace(WHITESPACE, ' ')
    .trim()
}

async function createSanitizer(): Promise<TextTransform> {
  const { default: createDomPurify } = await import('dompurify')
  const purifier = createDomPurify(window)
  purifier.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A') {
      node.setAttribute('target', LINK_TARGET)
      node.setAttribute('rel', LINK_REL)
    }
  })
  return (html) =>
    purifier.sanitize(html, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
      ALLOWED_URI_REGEXP,
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false,
    })
}

async function createRenderer(): Promise<TextTransform> {
  const [{ default: MarkdownIt }, sanitize] = await Promise.all([
    import('markdown-it'),
    createSanitizer(),
  ])
  const parser = new MarkdownIt({ html: false, linkify: true }).disable('table')
  return (markdown) => sanitize(parser.render(markdown))
}

function loadRenderer(): Promise<TextTransform> {
  if (rendererPromise === null) {
    rendererPromise = createRenderer().catch((error: unknown) => {
      rendererPromise = null
      throw error
    })
  }
  return rendererPromise
}

export async function renderMarkdown(markdown: string): Promise<string> {
  const render = await loadRenderer()
  return render(markdown)
}
