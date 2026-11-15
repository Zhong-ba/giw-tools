import type { ReactNode } from 'react'

// Groups: 1-2 long comment, 3 line comment, 4-5 long string, 6 quoted string, 7 number, 8 keyword,
// 9 constant, 10 called function name. Unterminated comments and strings run to the end of the text or line.
const pattern = new RegExp([
  String.raw`(--\[(=*)\[[\s\S]*?(?:\]\2\]|(?![\s\S])))`,
  /(--[^\n]*)/.source,
  String.raw`(\[(=*)\[[\s\S]*?(?:\]\5\]|(?![\s\S])))`,
  /("(?:[^"\\\n]|\\[\s\S])*"?|'(?:[^'\\\n]|\\[\s\S])*'?)/.source,
  /(\b0[xX][0-9a-fA-F]+\b|\b\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)/.source,
  /\b(and|break|do|else|elseif|end|for|function|goto|if|in|local|not|or|repeat|return|then|until|while)\b/.source,
  /\b(true|false|nil|self)\b/.source,
  /\b([A-Za-z_]\w*)(?=\s*[({'"])/.source,
].join('|'), 'g')

const kinds = ['comment', 'comment', 'string', 'string', 'number', 'keyword', 'constant', 'function']
const groups = [1, 3, 4, 6, 7, 8, 9, 10]

export function highlightLua(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) nodes.push(text.slice(last, match.index))
    const kind = kinds[groups.findIndex(group => match[group] !== undefined)]
    nodes.push(<span key={nodes.length} className={`lua-${kind}`}>{match[0]}</span>)
    last = match.index + match[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}
