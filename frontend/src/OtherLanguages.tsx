import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ChevronRight, CircleAlert, Copy, LoaderCircle } from 'lucide-react'
import { api, message } from './api'
import type { LanguageResult } from './api'
import { findMatches, markMatches } from './search'
import { highlightWikitext } from './wikitext'
import { updateToolQuery } from './toolUrl'

const languages = ['CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'JP', 'KR', 'PT', 'RU', 'TH', 'VI', 'TR', 'IT']

function ResultCard({ result, query, translation, romanization, header }: {
  result: LanguageResult; query: string; translation: boolean; romanization: boolean; header: boolean
}) {
  const [removeTL, setRemoveTL] = useState(false)
  const [removeRM, setRemoveRM] = useState(false)
  const [copiedText, setCopiedText] = useState<string | null>(null)
  const [error, setError] = useState('')
  const template = result.text.split('\n').filter(line =>
    !((!translation || removeTL) && /^\|\w+_tl\s*=/.test(line)) &&
    !((!romanization || removeRM) && /^\|\w+_rm\s*=/.test(line)),
  ).join('\n')
  const text = (header ? '==Other Languages==\n' : '') + template
  const copied = copiedText === text
  useEffect(() => {
    if (copiedText === null) return
    const timer = setTimeout(() => setCopiedText(null), 2000)
    return () => clearTimeout(timer)
  }, [copiedText])
  const copy = async () => {
    setError('')
    try {
      await navigator.clipboard.writeText(text)
      setCopiedText(text)
    } catch (reason) { setError(message(reason)) }
  }
  return <details className="ol-result panel" open>
    <summary>
      <ChevronRight size={14} className="ol-result-chevron" aria-hidden="true" />
      <span>TextMapHash: <code>{result.textmap_hash}</code></span>
      <span className="ol-result-actions">
        <span className="ol-checkboxes" role="group" aria-label="Result Output Options">
          <label><input type="checkbox" checked={translation && !removeTL} disabled={!translation}
            onChange={event => setRemoveTL(!event.target.checked)} />Include _tl</label>
          <label><input type="checkbox" checked={romanization && !removeRM} disabled={!romanization}
            onChange={event => setRemoveRM(!event.target.checked)} />Include _rm</label>
        </span>
        <button className="button secondary small" onClick={event => { event.preventDefault(); void copy() }}>
          {copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}
        </button>
      </span>
    </summary>
    {error && <div className="error-box" role="alert"><CircleAlert size={16} />{error}</div>}
    <pre className="text-preview">{markMatches(highlightWikitext(text), findMatches(text, query), query.length, -1)}</pre>
  </details>
}

export function OtherLanguages() {
  const [initial] = useState(() => {
    const params = new URLSearchParams(location.search)
    const query = params.get('q')?.trim() ?? ''
    const language = params.get('input_lang') ?? 'EN'
    return { query: query.length <= 200 ? query : '', language: languages.includes(language) ? language : 'EN',
      translation: params.get('translation') !== 'false', romanization: params.get('romanization') !== 'false',
      header: params.get('header') === 'true' }
  })
  const [text, setText] = useState(initial.query)
  const [language, setLanguage] = useState(initial.language)
  const [linked, setLinked] = useState({ query: initial.query, language: initial.language })
  const [translation, setTranslation] = useState(initial.translation)
  const [romanization, setRomanization] = useState(initial.romanization)
  const [header, setHeader] = useState(initial.header)
  const [results, setResults] = useState<{ query: string; items: LanguageResult[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const request = useRef<AbortController | null>(null)
  const generate = useCallback(async (query: string, inputLanguage: string) => {
    if (!query) { setError('Enter a name or TextMapHash.'); return }
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setBusy(true); setError(''); setResults(null)
    setLinked({ query: query.length <= 200 ? query : '', language: inputLanguage })
    try {
      const items = await api<LanguageResult[]>('/other-languages', {
        method: 'POST', body: JSON.stringify({ text: query, input_lang: inputLanguage }), signal: controller.signal,
      })
      if (!controller.signal.aborted) setResults({ query, items })
    } catch (reason) { if (!controller.signal.aborted) setError(message(reason)) }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }, [])
  useEffect(() => {
    const start = setTimeout(() => { if (initial.query) void generate(initial.query, initial.language) }, 0)
    return () => { clearTimeout(start); request.current?.abort() }
  }, [generate, initial])
  const linkedLanguage = linked.query ? linked.language : language
  useEffect(() => {
    updateToolQuery('other-languages', { q: linked.query || undefined, input_lang: linkedLanguage === 'EN' ? undefined : linkedLanguage,
      translation: translation ? undefined : 'false', romanization: romanization ? undefined : 'false', header: header ? 'true' : undefined })
  }, [linked.query, linkedLanguage, translation, romanization, header])
  return <div className="dialog-body ol-screen">
    <form onSubmit={event => { event.preventDefault(); void generate(text.trim(), language) }}>
      {busy && <p>The first lookup for a dataset builds its persistent index. Subsequent lookups reuse it.</p>}
      <div className="ol-query">
        <label className="field">
          <span>Name or TextMapHash</span>
          <input autoFocus value={text} maxLength={20000} placeholder="Enter a name (case insensitive) or TextMapHash"
            onChange={event => setText(event.target.value)} />
        </label>
      </div>
      <div className="ol-options">
        <div className="ol-checkboxes" role="group" aria-label="Output Options">
          <label><input type="checkbox" checked={translation} onChange={event => setTranslation(event.target.checked)} />Include _tl</label>
          <label><input type="checkbox" checked={romanization} onChange={event => setRomanization(event.target.checked)} />Include _rm</label>
          <label><input type="checkbox" checked={header} onChange={event => setHeader(event.target.checked)} />Include Header</label>
        </div>
        <label className="field ol-language"><span>Input Language</span><select value={language} onChange={event => setLanguage(event.target.value)}>
          {languages.map(code => <option key={code} value={code}>{code}</option>)}
        </select></label>
        <button className="button primary" disabled={busy || !text.trim()} type="submit">
          {busy && <LoaderCircle size={16} className="spin" />}{busy ? 'Generating' : 'Generate'}
        </button>
      </div>
    </form>
    {error && <div className="error-box" role="alert"><CircleAlert size={18} />{error}</div>}
    {results && <section className="ol-results" aria-label="Other Languages Results">
      <h3>Total Results: {results.items.length}</h3>
      {results.items.map(result => <ResultCard key={`${results.query}:${result.textmap_hash}`} result={result}
        query={results.query} translation={translation} romanization={romanization} header={header} />)}
    </section>}
  </div>
}
