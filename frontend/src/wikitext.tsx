import type { ReactNode } from 'react'

// Groups: 1 comment, 2 page-info block, 3-5 heading, 6-7 template open + name, 8 template close,
// 9-10 link open + target, 11 link close, 12 line-start parameter, 13 pipe, 14 bold/italic, 15 HTML tag.
const pattern = new RegExp([
  /(<!--[\s\S]*?(?:-->|(?![\s\S])))/,
  /(<%--[\s\S]*?(?:--%>|(?![\s\S])))/,
  // String form: \3 refers to the opening "=" run's group number in the combined pattern.
  String.raw`^(={1,6})([^\n]*?)(\3)[ \t]*$`,
  /(\{\{)([^{}|\n]*)/,
  /(\}\})/,
  /(\[\[)([^[\]|\n]*)/,
  /(\]\])/,
  /^(\|[^=\n{}|[\]]*=)/,
  /(\|)/,
  /('{2,5})/,
  /(<\/?[a-zA-Z][^>\n]*>)/,
].map(part => typeof part === 'string' ? part : part.source).join('|'), 'gm')

export function highlightWikitext(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  const span = (kind: string, value: string) => nodes.push(<span key={nodes.length} className={`wt-${kind}`}>{value}</span>)
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) nodes.push(text.slice(last, match.index))
    if (match[1] ?? match[2]) span('comment', match[0])
    else if (match[3]) span('heading', match[0])
    else if (match[6]) { span('brace', match[6]); if (match[7]) span('template', match[7]) }
    else if (match[8]) span('brace', match[8])
    else if (match[9]) { span('bracket', match[9]); if (match[10]) span('link', match[10]) }
    else if (match[11]) span('bracket', match[11])
    else if (match[12]) span('param', match[12])
    else if (match[13]) span('pipe', match[13])
    else if (match[14]) span('quote', match[14])
    else span('tag', match[0])
    last = match.index + match[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}
