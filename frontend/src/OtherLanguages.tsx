import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Check, CircleAlert, Copy, LoaderCircle } from 'lucide-react'
import { api, message } from './api'
import type { LanguageResult } from './api'
import { findMatches, markMatches } from './search'
import { highlightWikitext } from './wikitext'

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
      <span>TextMapHash: <code>{result.textmap_hash}</code></span>
      <button className="button secondary small" onClick={event => { event.preventDefault(); void copy() }}>
        {copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}
      </button>
    </summary>
    <div className="ol-result-actions">
      <button className="text-button" disabled={!romanization} onClick={() => setRemoveRM(!removeRM)}>{removeRM ? 'Restore RM' : 'Remove RM'}</button>
      <button className="text-button" disabled={!translation} onClick={() => setRemoveTL(!removeTL)}>{removeTL ? 'Restore TL' : 'Remove TL'}</button>
    </div>
    {error && <div className="error-box" role="alert"><CircleAlert size={16} />{error}</div>}
    <pre className="text-preview">{markMatches(highlightWikitext(text), findMatches(text, query), query.length, -1)}</pre>
  </details>
}

export function OtherLanguages() {
  const [text, setText] = useState('')
  const [language, setLanguage] = useState('EN')
  const [translation, setTranslation] = useState(true)
  const [romanization, setRomanization] = useState(true)
  const [header, setHeader] = useState(false)
  const [results, setResults] = useState<{ query: string; items: LanguageResult[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  const generate = async (event: FormEvent) => {
    event.preventDefault()
    const query = text.trim()
    if (!query) { setError('Enter a name or TextMapHash.'); return }
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setBusy(true); setError(''); setResults(null)
    try {
      const items = await api<LanguageResult[]>('/other-languages', {
        method: 'POST', body: JSON.stringify({ text: query, input_lang: language }), signal: controller.signal,
      })
      if (!controller.signal.aborted) setResults({ query, items })
    } catch (reason) { if (!controller.signal.aborted) setError(message(reason)) }
    finally { if (!controller.signal.aborted) setBusy(false) }
  }
  return <div className="dialog-body ol-screen">
    <form onSubmit={event => { void generate(event) }}>
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
