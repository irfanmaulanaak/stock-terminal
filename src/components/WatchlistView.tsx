import { Fragment, useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { StockChart } from '../StockChart'
import { localizedStatus, tr } from '../i18n'
import type { FilterConfidence, FilterDirection, Language, QuoteState, Row, SortDirection, SortKey, StatusFilter } from '../types'
import { formatPercent, formatPrice, movementClass } from '../utils'
import { QuoteStatus } from './QuoteStatus'

interface Props { language: Language; rows: Row[]; universeCount: number; quoteState: QuoteState; lastRefresh: string | null; quoteError: string; expanded: string | null; onToggle: (symbol: string) => void; onClearExpanded: () => void }

function SortButton({ label, column, sort, onSort }: { label: string; column: SortKey; sort: { key: SortKey; direction: SortDirection }; onSort: (key: SortKey) => void }) {
  const active = sort.key === column
  return <button className={`sort-button ${active ? 'active' : ''}`} onClick={() => onSort(column)} type="button">{label}<span>{active ? (sort.direction === 'asc' ? '↑' : '↓') : '↕'}</span></button>
}

export function WatchlistView({ language, rows, universeCount, quoteState, lastRefresh, quoteError, expanded, onToggle, onClearExpanded }: Props) {
  const [query, setQuery] = useState('')
  const [direction, setDirection] = useState<FilterDirection>('ALL')
  const [confidence, setConfidence] = useState<FilterConfidence>('ALL')
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({ key: 'symbol', direction: 'asc' })
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(1)

  const visibleRows = useMemo(() => {
    const search = query.trim().toUpperCase()
    const filtered = rows.filter(({ stock, status: rowStatus }) => (!search || stock.symbol.includes(search)) && (direction === 'ALL' || stock.forecast === direction) && (confidence === 'ALL' || stock.confidence === confidence) && (status === 'ALL' || rowStatus.label === status))
    const confidenceRank = { low: 1, medium: 2, high: 3 }
    return filtered.sort((a, b) => {
      const value = (row: Row): string | number => ({ symbol: row.stock.symbol, baseline: row.stock.baseline, live: row.live ?? -Infinity, movement: row.movement ?? -Infinity, forecast: { UP: 3, FLAT: 2, DOWN: 1 }[row.stock.forecast], confidence: confidenceRank[row.stock.confidence], status: row.status.label }[sort.key])
      const left = value(a); const right = value(b)
      const compared = typeof left === 'string' && typeof right === 'string' ? left.localeCompare(right) : Number(left) - Number(right)
      return sort.direction === 'asc' ? compared : -compared
    })
  }, [confidence, direction, query, rows, sort, status])
  const pageCount = Math.max(1, Math.ceil(visibleRows.length / pageSize))
  const paginatedRows = useMemo(() => visibleRows.slice((page - 1) * pageSize, page * pageSize), [page, pageSize, visibleRows])
  useEffect(() => setPage(1), [confidence, direction, pageSize, query, sort.direction, sort.key, status])
  useEffect(() => setPage((current) => Math.min(current, pageCount)), [pageCount])
  useEffect(() => { if (expanded && !paginatedRows.some(({ stock }) => stock.symbol === expanded)) onClearExpanded() }, [expanded, onClearExpanded, paginatedRows])

  const changeSort = (key: SortKey) => setSort((current) => current.key === key ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' } : { key, direction: key === 'symbol' ? 'asc' : 'desc' })
  const toggle = onToggle
  const keyDown = (event: KeyboardEvent<HTMLTableRowElement>, symbol: string) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onToggle(symbol) } }
  const reset = () => { setQuery(''); setDirection('ALL'); setConfidence('ALL'); setStatus('ALL') }

  return <section className="watchlist-section">
    <div className="watchlist-header"><div><div className="section-kicker">{tr(language, 'coverage')}</div><h3>{tr(language, 'watchlist')}</h3><span className="subtle">{visibleRows.length} of {universeCount} symbols</span></div><QuoteStatus {...{ language, quoteState, lastRefresh, quoteError }} /></div>
    <div className="controls" aria-label={tr(language, 'filterBy')}><div className="filter-bar-title">{tr(language, 'filterBy')}</div>
      <label className="filter-field filter-search"><span>{tr(language, 'search')}</span><span className="search-box"><span aria-hidden="true">⌕</span><input aria-label={tr(language, 'search')} onChange={(event) => setQuery(event.target.value)} placeholder={`${tr(language, 'symbol')}...`} value={query} /></span></label>
      <label className="filter-field"><span>{tr(language, 'forecast')}</span><select aria-label={tr(language, 'forecast')} onChange={(event) => setDirection(event.target.value as FilterDirection)} value={direction}><option value="ALL">{tr(language, 'allForecasts')}</option><option value="UP">UP</option><option value="FLAT">FLAT</option><option value="DOWN">DOWN</option></select></label>
      <label className="filter-field"><span>{tr(language, 'confidence')}</span><select aria-label={tr(language, 'confidence')} onChange={(event) => setConfidence(event.target.value as FilterConfidence)} value={confidence}><option value="ALL">{tr(language, 'allConfidence')}</option><option value="high">{tr(language, 'high')}</option><option value="medium">{tr(language, 'medium')}</option><option value="low">{tr(language, 'low')}</option></select></label>
      <label className="filter-field"><span>{tr(language, 'status')}</span><select aria-label={tr(language, 'status')} onChange={(event) => setStatus(event.target.value as StatusFilter)} value={status}><option value="ALL">{tr(language, 'allStatuses')}</option>{(['On track', 'Counter', 'In range', 'Watching', 'Unavailable', 'Pending'] as Exclude<StatusFilter, 'ALL'>[]).map((item) => <option key={item} value={item}>{localizedStatus(language, item)}</option>)}</select></label>
      {(Boolean(query.trim()) || direction !== 'ALL' || confidence !== 'ALL' || status !== 'ALL') && <button className="reset-filters" onClick={reset} type="button">{tr(language, 'resetFilters')}</button>}
    </div>
    <div className="pagination-toolbar" aria-label={`${tr(language, 'watchlist')} ${tr(language, 'pagination')}`}><span className="pagination-count">{visibleRows.length} {tr(language, 'filteredCount')}</span><div className="pagination-controls"><label className="pagination-size"><span>{tr(language, 'rowsPerPage')}</span><select aria-label={tr(language, 'rowsPerPage')} value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option></select></label><button className="pagination-button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} type="button">{tr(language, 'previous')}</button><span className="pagination-indicator" aria-live="polite">{tr(language, 'page')} {page} {tr(language, 'pageOf')} {pageCount} {tr(language, 'pageSuffix')}</span><button className="pagination-button" disabled={page >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))} type="button">{tr(language, 'next')}</button></div></div>
    <div className="table-wrap"><table><thead><tr><th><SortButton column="symbol" label={tr(language, 'symbol')} onSort={changeSort} sort={sort} /></th><th className="numeric-heading"><SortButton column="baseline" label={tr(language, 'baseline')} onSort={changeSort} sort={sort} /></th><th className="numeric-heading"><SortButton column="live" label={tr(language, 'livePrice')} onSort={changeSort} sort={sort} /></th><th className="numeric-heading"><SortButton column="movement" label={tr(language, 'movement')} onSort={changeSort} sort={sort} /></th><th><SortButton column="forecast" label={tr(language, 'forecast')} onSort={changeSort} sort={sort} /></th><th><SortButton column="confidence" label={tr(language, 'confidence')} onSort={changeSort} sort={sort} /></th><th><SortButton column="status" label={tr(language, 'status')} onSort={changeSort} sort={sort} /></th></tr></thead>
      <tbody>{paginatedRows.map(({ stock, quote, live, movement, status: rowStatus }) => { const isExpanded = expanded === stock.symbol; return <Fragment key={stock.symbol}><tr className={`expandable-row ${isExpanded ? 'expanded' : ''}`} aria-label={`${stock.symbol}: ${tr(language, 'chartHint')}`} title={tr(language, 'chartHint')} aria-expanded={isExpanded} tabIndex={0} onClick={() => toggle(stock.symbol)} onKeyDown={(event) => keyDown(event, stock.symbol)}><td><span className="symbol">{stock.symbol}</span><span className="exchange">.JK</span></td><td className="numeric">{formatPrice(stock.baseline)}</td><td className="numeric live-price">{formatPrice(live)}</td><td className={`numeric ${movementClass(movement)}`}>{formatPercent(movement)}</td><td><span className={`forecast-badge ${stock.forecast.toLowerCase()}`}><span>{stock.forecast === 'UP' ? '↗' : stock.forecast === 'DOWN' ? '↘' : '→'}</span>{stock.forecast}</span><span className="target">{formatPercent(stock.target_return_pct, 1)} target</span></td><td><span className={`confidence ${stock.confidence}`}><i />{stock.confidence}</span></td><td><span className={`status-pill ${rowStatus.tone}`}>{localizedStatus(language, rowStatus.label)}</span>{quote?.error && <span className="row-error" title={quote.error}>!</span>}</td></tr>{isExpanded && <tr className="chart-detail-row"><td colSpan={7}><StockChart language={language} symbol={stock.symbol} forecast={stock} quote={quote} /></td></tr>}</Fragment> })}</tbody>
    </table>{!visibleRows.length && <div className="empty-state">No symbols match the current filters.</div>}</div>
  </section>
}
