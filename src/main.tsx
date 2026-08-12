import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { FocusSignals } from './components/FocusSignals'
import { PortfolioView } from './components/PortfolioView'
import { WatchlistView } from './components/WatchlistView'
import { TransparencyPanel } from './components/TransparencyPanel'
import { tr } from './i18n'
import type { AuditPayload, DashboardPayload, DashboardView, FocusRow, Language, MethodologyPayload, PortfolioRow, Quote, QuotePayload, QuoteState, Row } from './types'
import { focusScore, formatDate, formatPercent, formatPrice, livePriceFor, portfolioPositions, portfolioSymbols, statusFor } from './utils'
import './styles.css'

function App() {
  const [data, setData] = useState<DashboardPayload | null>(null)
  const [quotes, setQuotes] = useState<Record<string, Quote>>({})
  const [view, setView] = useState<DashboardView>('watchlist')
  const [language, setLanguage] = useState<Language>(() => {
    const saved = window.localStorage.getItem('stock-dashboard-language')
    return saved === 'ID' || saved === 'MY' || saved === 'CN' ? saved : 'EN'
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [quoteState, setQuoteState] = useState<QuoteState>('idle')
  const [quoteError, setQuoteError] = useState('')
  const [lastRefresh, setLastRefresh] = useState<string | null>(null)
  const [expandedChart, setExpandedChart] = useState<{ symbol: string; area: 'focus' | 'watchlist' } | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [audit, setAudit] = useState<AuditPayload | null>(null)
  const [methodology, setMethodology] = useState<MethodologyPayload | null>(null)
  const [transparencyLoading, setTransparencyLoading] = useState(true)
  const [transparencyError, setTransparencyError] = useState('')

  const refreshQuotes = useCallback(async () => {
    setQuoteState('loading')
    setQuoteError('')
    try {
      const fetchQuotes = async (path: string) => {
        const response = await fetch(path)
        const payload = (await response.json()) as QuotePayload & { error?: string }
        if (!response.ok) throw new Error(payload.error || 'Quote refresh failed')
        return payload
      }
      const payloads = await Promise.all([fetchQuotes('/api/quotes'), fetchQuotes(`/api/quotes?symbols=${portfolioSymbols.join(',')}`)])
      const allQuotes = payloads.flatMap((payload) => payload.quotes)
      const pricedQuotes = allQuotes.filter((quote) => quote.price !== undefined && Number.isFinite(quote.price))
      const unavailableCount = allQuotes.length - pricedQuotes.length
      setQuotes(Object.fromEntries(allQuotes.map((quote) => [quote.symbol, quote])))
      setLastRefresh(payloads.map((payload) => payload.fetchedAt).sort().at(-1) || null)
      setQuoteState(pricedQuotes.length ? 'ready' : 'error')
      if (!pricedQuotes.length) setQuoteError('Yahoo quotes are unavailable right now.')
      else if (unavailableCount) setQuoteError(`${unavailableCount} quote${unavailableCount === 1 ? '' : 's'} unavailable.`)
    } catch (caught) {
      setQuoteState('error')
      setQuoteError(caught instanceof Error ? caught.message : 'Quote refresh failed')
    }
  }, [])

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/dashboard')
      const payload = (await response.json()) as DashboardPayload & { error?: string }
      if (!response.ok) throw new Error(payload.error || 'Forecast load failed')
      setData(payload); setError(''); setLoading(false); void refreshQuotes()
    } catch (caught) {
      setLoading(false); setError(caught instanceof Error ? caught.message : 'Forecast load failed')
    }
  }, [refreshQuotes])

  useEffect(() => { window.localStorage.setItem('stock-dashboard-language', language) }, [language])
  useEffect(() => {
    void loadDashboard()
    const interval = window.setInterval(() => void refreshQuotes(), 60000)
    return () => window.clearInterval(interval)
  }, [loadDashboard, refreshQuotes])
  useEffect(() => {
    let active = true
    const loadTransparency = async () => {
      setTransparencyLoading(true); setTransparencyError('')
      try {
        const [auditResponse, methodologyResponse] = await Promise.all([fetch('/api/audit'), fetch('/api/methodology')])
        const [auditPayload, methodologyPayload] = await Promise.all([auditResponse.json(), methodologyResponse.json()])
        if (!auditResponse.ok || !methodologyResponse.ok) throw new Error(auditPayload.error || methodologyPayload.error || 'Request failed')
        if (active) { setAudit(auditPayload as AuditPayload); setMethodology(methodologyPayload as MethodologyPayload); setTransparencyLoading(false) }
      } catch (caught) {
        if (active) { setTransparencyError(caught instanceof Error ? caught.message : 'Request failed'); setTransparencyLoading(false) }
      }
    }
    void loadTransparency()
    return () => { active = false }
  }, [])

  const rows = useMemo<Row[]>(() => data?.forecast.stocks.map((stock) => {
    const quote = quotes[stock.symbol]
    const live = livePriceFor(quote)
    const movement = live === null ? null : ((live - stock.baseline) / stock.baseline) * 100
    return { stock, quote, live, movement, status: statusFor(stock, quote, live) }
  }) || [], [data, quotes])
  const focusRows = useMemo<FocusRow[]>(() => rows.filter(({ stock }) => stock.forecast === 'UP').map((row) => ({ ...row, score: focusScore(row.stock) })).sort((a, b) => b.score - a.score || b.stock.target_return_pct - a.stock.target_return_pct || a.stock.symbol.localeCompare(b.stock.symbol)).slice(0, 5), [rows])
  const portfolioRows = useMemo<PortfolioRow[]>(() => portfolioPositions.map((position) => {
    const quote = quotes[position.symbol]; const live = livePriceFor(quote); const shares = position.lots * 100
    const currentValue = live === null ? null : live * shares; const pnl = currentValue === null ? null : currentValue - position.invested
    return { ...position, quote, shares, live, currentValue, pnl, pnlPct: pnl === null ? null : (pnl / position.invested) * 100, weight: null }
  }), [quotes])
  const currentValue = useMemo(() => portfolioRows.some((row) => row.currentValue === null) ? null : portfolioRows.reduce((total, row) => total + (row.currentValue || 0), 0), [portfolioRows])
  const weightedRows = useMemo(() => portfolioRows.map((row) => ({ ...row, weight: currentValue === null || row.currentValue === null || currentValue === 0 ? null : row.currentValue / currentValue * 100 })), [currentValue, portfolioRows])
  const investedTotal = portfolioPositions.reduce((total, position) => total + position.invested, 0)
  const portfolioPnl = currentValue === null ? null : currentValue - investedTotal
  const counts = useMemo(() => rows.reduce((result, row) => { result[row.stock.forecast] += 1; return result }, { UP: 0, FLAT: 0, DOWN: 0 }), [rows])
  const clearWatchlistChart = useCallback(() => setExpandedChart((current) => current?.area === 'watchlist' ? null : current), [])

  if (loading && !data) return <main className="app-shell centered"><div className="loading-state"><span className="spinner" />Loading forecast universe…</div></main>
  if (error && !data) return <main className="app-shell centered"><div className="error-panel"><span className="error-icon">!</span><h1>Data source unavailable</h1><p>{error}</p><button className="button" onClick={() => void loadDashboard()} type="button">Try again</button></div></main>
  if (!data) return null
  const { forecast, verification } = data
  const commonQuoteProps = { quoteState, lastRefresh, quoteError }
  const toggleChart = (symbol: string, area: 'focus' | 'watchlist') => {
    setSelectedSymbol(symbol)
    setExpandedChart((current) => current?.symbol === symbol && current.area === area ? null : { symbol, area })
  }

  return <main className="app-shell">
    <header className="topbar"><div className="brand"><div className="brand-mark"><span>↗</span></div><div><div className="eyebrow">HERMES / {tr(language, 'market')}</div><h1>Stock analytics</h1></div></div><div className="topbar-right"><label className="language-picker"><span>{tr(language, 'lang')}</span><select aria-label={tr(language, 'lang')} value={language} onChange={(event) => setLanguage(event.target.value as Language)}>{(['EN', 'ID', 'MY', 'CN'] as Language[]).map((item) => <option key={item} value={item}>{item}</option>)}</select></label><div className="read-only"><span className="live-dot" />{tr(language, 'readOnly')}</div><button className="refresh-button" onClick={() => void refreshQuotes()} disabled={quoteState === 'loading'} type="button"><span className={quoteState === 'loading' ? 'spinner small' : ''}>{quoteState === 'loading' ? '' : '↻'}</span>{quoteState === 'loading' ? tr(language, 'refreshing') : tr(language, 'refresh')}</button></div></header>
    <section className="intro-row"><div><div className="eyebrow accent">{view === 'watchlist' ? tr(language, 'watchPulse') : tr(language, 'portfolioView')} <span className="divider">/</span> {formatDate(forecast.as_of)} UTC+7</div><h2>{view === 'watchlist' ? tr(language, 'signals') : tr(language, 'positions')}</h2><p>{view === 'watchlist' ? tr(language, 'watchDesc') : tr(language, 'portfolioDesc')}</p></div><div className="intro-meta"><span>{forecast.universe_count} symbols</span><span>Threshold ±{forecast.actual_threshold_pct.toFixed(2)}%</span></div></section>
    <section className="view-toolbar" aria-label="Dashboard views"><div><div className="section-kicker">{tr(language, 'workspace')}</div><span className="subtle">{tr(language, 'switchHelp')}</span></div><div className="view-switch" role="tablist" aria-label="Dashboard view"><button aria-selected={view === 'watchlist'} className={view === 'watchlist' ? 'selected' : ''} onClick={() => setView('watchlist')} role="tab" type="button">{tr(language, 'watchlist')}</button><button aria-selected={view === 'portfolio'} className={view === 'portfolio' ? 'selected' : ''} onClick={() => setView('portfolio')} role="tab" type="button">{tr(language, 'portfolio')}</button></div></section>
    <div className="workspace-layout"><div className="primary-column">{view === 'watchlist' ? <><FocusSignals language={language} rows={focusRows} expanded={expandedChart?.area === 'focus' ? expandedChart.symbol : null} selectedSymbol={selectedSymbol} onToggle={(symbol) => toggleChart(symbol, 'focus')} /><WatchlistView language={language} rows={rows} universeCount={forecast.universe_count} {...commonQuoteProps} expanded={expandedChart?.area === 'watchlist' ? expandedChart.symbol : null} onToggle={(symbol) => toggleChart(symbol, 'watchlist')} onClearExpanded={clearWatchlistChart} /></> : <PortfolioView language={language} rows={weightedRows} currentValue={currentValue} investedTotal={investedTotal} pnl={portfolioPnl} pnlPct={portfolioPnl === null ? null : portfolioPnl / investedTotal * 100} {...commonQuoteProps} />}</div>
      <aside className="context-column" aria-label="Market context"><section className="context-block benchmark-block"><div className="section-kicker">{tr(language, 'benchmark')} / {forecast.benchmark.symbol}</div><div className="benchmark-value">{formatPrice(forecast.benchmark.displayed_price)}</div><div className="positive">{formatPercent(forecast.benchmark.displayed_change_pct)} today</div><span className="context-note">Forecast threshold ±{forecast.actual_threshold_pct.toFixed(2)}%</span></section>{view === 'watchlist' && <><section className="context-block"><div className="section-kicker">SIGNAL MIX</div><div className="signal-counts"><span className="positive"><strong>{counts.UP}</strong> UP</span><span className="neutral"><strong>{counts.FLAT}</strong> FLAT</span><span className="negative"><strong>{counts.DOWN}</strong> DOWN</span></div></section><section className="context-block"><div className="section-kicker">VERIFICATION</div><div className="context-value">{verification?.metrics.accuracy == null ? 'Pending' : `${verification.metrics.accuracy.toFixed(1)}%`}</div><span className="context-note">{verification ? `${verification.metrics.evaluated ?? '—'} observations scored` : 'Mount report to score forecasts'}</span></section></>}<section className="context-block context-footnote"><div className="section-kicker">READ-ONLY CONTEXT</div><p>Forecasts are saved snapshots. Live prices refresh independently from Yahoo Finance.</p><span className="context-note">As of {formatDate(forecast.as_of)} UTC+7</span></section></aside>
    </div>
    <TransparencyPanel language={language} audit={audit} methodology={methodology} loading={transparencyLoading} error={transparencyError} />
    <footer><span>Source · {forecast.source}</span><span>{verification ? `Verification · ${verification.format} report mounted` : 'Verification · report not mounted'}</span><span>Live quotes · Yahoo Finance chart API</span></footer>
  </main>
}

export default App
createRoot(document.getElementById('root')!).render(<App />)
