export function updateToolQuery(tool: string, values: Record<string, string | undefined>) {
  const url = new URL(window.location.href)
  if (url.pathname.replace(/\/+$/, '') !== `/${tool}`) return
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined) url.searchParams.delete(key)
    else url.searchParams.set(key, value)
  }
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, '', url)
}
