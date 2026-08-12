import { Fragment, useCallback, useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { createRoot } from 'react-dom/client'
import { StockChart } from './StockChart'
import { ResearchPanel } from './ResearchPanel'
import './styles.css'

type Direction = 'UP' | 'FLAT' | 'DOWN'
type Confidence = 'low' | 'medium' | 'high'
type FilterDirection = Direction | 'ALL'
type FilterConfidence = Confidence | 'ALL'
type StatusFilter = 'ALL' | 'On track' | 'Counter' | 'In range' | 'Watching' | 'Unavailable' | 'Pending'
type SortKey = 'symbol' | 'baseline' | 'live' | 'movement' | 'forecast' | 'confidence' | 'status'
type SortDirection = 'asc' | 'desc'
type DashboardView = 'watchlist' | 'portfolio'
type Language = 'EN' | 'ID' | 'MY' | 'CN'

interface ForecastStock {
  symbol: string
  baseline: number
  baseline_change_pct: number
  forecast: Direction
  target_return_pct: number
  confidence: Confidence
}

interface Forecast {
  as_of: string
  source: string
  actual_threshold_pct: number
  universe_count: number
  benchmark: { symbol: string; displayed_price: number; displayed_change_pct: number }
  stocks: ForecastStock[]
}

interface Verification {
  path: string
  format: string
  metrics: {
    accuracy: number | null
    directionalAccuracy: number | null
    correct: number | null
    evaluated: number | null
  }
}

interface DashboardPayload {
  forecast: Forecast
  verification: Verification | null
}

interface Quote {
  symbol: string
  yahooSymbol: string
  price?: number
  previousClose?: number | null
  change?: number | null
  changePct?: number | null
  asOf?: string | null
  error?: string
}

interface QuotePayload {
  quotes: Quote[]
  fetchedAt: string
  source: string
}

interface Row {
  stock: ForecastStock
  quote?: Quote
  live: number | null
  movement: number | null
  status: { label: string; tone: 'good' | 'warn' | 'muted' }
}

interface FocusRow extends Row {
  score: number
}

interface PortfolioPosition {
  symbol: string
  lots: number
  averageCost: number
  invested: number
}

interface PortfolioRow extends PortfolioPosition {
  quote?: Quote
  shares: number
  live: number | null
  currentValue: number | null
  pnl: number | null
  pnlPct: number | null
  weight: number | null
}

const LOT_SIZE = 100
const portfolioPositions: PortfolioPosition[] = [
  { symbol: 'BBCA', lots: 9, averageCost: 6009, invested: 5408100 },
  { symbol: 'BNBR', lots: 166.96, averageCost: 156.34, invested: 2610289 },
  { symbol: 'ELTY', lots: 125, averageCost: 43.96, invested: 549623 },
  { symbol: 'PRDL', lots: 1, averageCost: 120, invested: 12000 },
]
const portfolioSymbols = portfolioPositions.map((position) => position.symbol)

const money = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const preciseNumber = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const dateTime = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
})

const copy: Record<Language, Record<string, string>> = {
  EN: {
    market: 'MARKET INTELLIGENCE', readOnly: 'READ-ONLY MONITOR', refresh: 'Refresh quotes', refreshing: 'Refreshing',
    watchPulse: 'WATCHLIST PULSE', portfolioView: 'PORTFOLIO VIEW', signals: 'Signals, without the noise.', positions: 'Positions, at a glance.',
    watchDesc: 'Heuristic forecasts with live market quotes.', portfolioDesc: 'Saved positions marked to live quotes.', workspace: 'WORKSPACE', switchHelp: 'Switch between signals and positions.',
    watchlist: 'Watchlist', portfolio: 'Portfolio', priority: 'PRIORITY SIGNALS', top5: 'Top 5 Focus', shortlist: 'Research shortlist', noOrder: 'Not a buy order',
    rank: 'Rank', symbol: 'Symbol', confidence: 'Confidence', currentMove: 'Current move', forecastTarget: 'Forecast target', livePrice: 'Live price', riskFlag: 'Risk flag',
    coverage: 'COVERAGE', baseline: 'Baseline', movement: 'Movement', forecast: 'Forecast', status: 'Status', filterBy: 'Filter by', search: 'Search', allForecasts: 'All forecasts', allConfidence: 'All confidence', allStatuses: 'All statuses', high: 'High', medium: 'Medium', low: 'Low', highConfidence: 'High confidence', mediumConfidence: 'Medium confidence', lowConfidence: 'Low confidence', resetFilters: 'Reset filters',
    onTrack: 'On track', counter: 'Counter', inRange: 'In range', watching: 'Watching', unavailable: 'Unavailable', pending: 'Pending',
    benchmark: 'BENCHMARK', signalMix: 'SIGNAL MIX', verification: 'VERIFICATION', readOnlyContext: 'READ-ONLY CONTEXT',
    liveIndependent: 'Forecasts are saved snapshots. Live prices refresh independently from Yahoo Finance.',
    moveTip: 'Live price movement versus the saved forecast baseline.', targetTip: 'Expected percentage move for the next checkpoint. This is not a price.',
    riskTip: 'A flag for extension, volatility, liquidity, or data risk. It is not a buy or sell recommendation.', confidenceTip: 'Heuristic conviction. It is not a calibrated probability.', forecastTip: 'UP, FLAT, or DOWN scenario for the next checkpoint. It is not a guarantee.',
    method: 'How the ranking works', lang: 'Language', source: 'Source', liveQuotes: 'Live quotes', chartHint: 'Click a row to open its chart', closeChart: 'Close chart',
    filteredCount: 'filtered', rowsPerPage: 'Rows per page', previous: 'Previous', next: 'Next', page: 'Page', pageOf: 'of', pageSuffix: '', pagination: 'Pagination',
  },
  ID: {
    market: 'INTELIJEN PASAR', readOnly: 'MONITOR BACA SAJA', refresh: 'Segarkan harga', refreshing: 'Menyegarkan',
    watchPulse: 'PANTAUAN WATCHLIST', portfolioView: 'TAMPILAN PORTOFOLIO', signals: 'Sinyal yang mudah dibaca.', positions: 'Posisi dalam satu tampilan.',
    watchDesc: 'Forecast heuristik dengan harga pasar live.', portfolioDesc: 'Posisi tersimpan berdasarkan harga live.', workspace: 'RUANG KERJA', switchHelp: 'Pilih sinyal atau posisi.',
    watchlist: 'Watchlist', portfolio: 'Portofolio', priority: 'SINYAL PRIORITAS', top5: '5 Fokus Utama', shortlist: 'Daftar riset', noOrder: 'Bukan perintah beli',
    rank: 'Peringkat', symbol: 'Kode', confidence: 'Keyakinan', currentMove: 'Pergerakan kini', forecastTarget: 'Target forecast', livePrice: 'Harga live', riskFlag: 'Tanda risiko',
    coverage: 'CAKUPAN', baseline: 'Baseline', movement: 'Pergerakan', forecast: 'Forecast', status: 'Status', filterBy: 'Filter berdasarkan', search: 'Cari', allForecasts: 'Semua forecast', allConfidence: 'Semua keyakinan', allStatuses: 'Semua status', high: 'Tinggi', medium: 'Sedang', low: 'Rendah', highConfidence: 'Keyakinan tinggi', mediumConfidence: 'Keyakinan sedang', lowConfidence: 'Keyakinan rendah', resetFilters: 'Reset filter',
    onTrack: 'Sesuai arah', counter: 'Berlawanan', inRange: 'Dalam rentang', watching: 'Pantau', unavailable: 'Tidak tersedia', pending: 'Menunggu',
    benchmark: 'BENCHMARK', signalMix: 'KOMPOSISI SINYAL', verification: 'VERIFIKASI', readOnlyContext: 'KONTEKS BACA SAJA',
    liveIndependent: 'Forecast tersimpan. Harga live diperbarui terpisah dari Yahoo Finance.',
    moveTip: 'Pergerakan harga live dibandingkan baseline forecast tersimpan.', targetTip: 'Perkiraan persentase gerak sampai checkpoint berikutnya. Ini bukan harga.',
    riskTip: 'Tanda risiko dari kenaikan berlebih, volatilitas, likuiditas, atau kualitas data. Bukan rekomendasi beli atau jual.', confidenceTip: 'Keyakinan heuristik. Bukan probabilitas terkalibrasi.', forecastTip: 'Skenario UP, FLAT, atau DOWN untuk checkpoint berikutnya. Bukan jaminan.',
    method: 'Cara peringkat bekerja', lang: 'Bahasa', source: 'Sumber', liveQuotes: 'Harga live', chartHint: 'Klik baris untuk membuka grafik', closeChart: 'Tutup grafik',
    filteredCount: 'tersaring', rowsPerPage: 'Baris per halaman', previous: 'Sebelumnya', next: 'Berikutnya', page: 'Halaman', pageOf: 'dari', pageSuffix: '', pagination: 'Paginasi',
  },
  MY: {
    market: 'INTELIJEN PASAR', readOnly: 'PEMANTAU BACA SAHAJA', refresh: 'Segar harga', refreshing: 'Sedang segar',
    watchPulse: 'PANTAUAN WATCHLIST', portfolioView: 'PAPARAN PORTFOLIO', signals: 'Isyarat yang mudah dibaca.', positions: 'Posisi dalam satu paparan.',
    watchDesc: 'Ramalan heuristik dengan harga pasaran live.', portfolioDesc: 'Posisi tersimpan berdasarkan harga live.', workspace: 'RUANG KERJA', switchHelp: 'Pilih isyarat atau posisi.',
    watchlist: 'Watchlist', portfolio: 'Portfolio', priority: 'ISYARAT KEUTAMAAN', top5: '5 Fokus Utama', shortlist: 'Senarai kajian', noOrder: 'Bukan arahan beli',
    rank: 'Kedudukan', symbol: 'Kod', confidence: 'Keyakinan', currentMove: 'Pergerakan kini', forecastTarget: 'Sasaran ramalan', livePrice: 'Harga live', riskFlag: 'Tanda risiko',
    coverage: 'LIPUTAN', baseline: 'Baseline', movement: 'Pergerakan', forecast: 'Ramalan', status: 'Status', filterBy: 'Tapis mengikut', search: 'Cari', allForecasts: 'Semua ramalan', allConfidence: 'Semua keyakinan', allStatuses: 'Semua status', high: 'Tinggi', medium: 'Sederhana', low: 'Rendah', highConfidence: 'Keyakinan tinggi', mediumConfidence: 'Keyakinan sederhana', lowConfidence: 'Keyakinan rendah', resetFilters: 'Tetap semula penapis',
    onTrack: 'Mengikut arah', counter: 'Berlawanan', inRange: 'Dalam julat', watching: 'Pantau', unavailable: 'Tidak tersedia', pending: 'Menunggu',
    benchmark: 'PENANDA ARAS', signalMix: 'CAMPURAN ISYARAT', verification: 'PENGESAHAN', readOnlyContext: 'KONTEKS BACA SAHAJA',
    liveIndependent: 'Ramalan disimpan. Harga live dikemas kini secara berasingan daripada Yahoo Finance.',
    moveTip: 'Pergerakan harga live berbanding baseline ramalan yang disimpan.', targetTip: 'Anggaran pergerakan peratus untuk checkpoint seterusnya. Ini bukan harga.',
    riskTip: 'Tanda risiko untuk kenaikan berlebihan, turun naik, kecairan, atau kualiti data. Bukan cadangan beli atau jual.', confidenceTip: 'Keyakinan heuristik. Bukan kebarangkalian yang ditentukur.', forecastTip: 'Senario UP, FLAT, atau DOWN untuk checkpoint seterusnya. Bukan jaminan.',
    method: 'Cara kedudukan dikira', lang: 'Bahasa', source: 'Sumber', liveQuotes: 'Harga live', chartHint: 'Klik baris untuk membuka graf', closeChart: 'Tutup graf',
    filteredCount: 'ditapis', rowsPerPage: 'Baris setiap halaman', previous: 'Sebelumnya', next: 'Seterusnya', page: 'Halaman', pageOf: 'daripada', pageSuffix: '', pagination: 'Paginasi',
  },
  CN: {
    market: '市场情报', readOnly: '只读监控', refresh: '刷新价格', refreshing: '正在刷新',
    watchPulse: '自选股动态', portfolioView: '投资组合', signals: '清晰的信号。', positions: '一目了然的持仓。',
    watchDesc: '启发式预测与实时市场价格。', portfolioDesc: '按实时价格计算的持仓。', workspace: '工作区', switchHelp: '切换信号或持仓。',
    watchlist: '自选股', portfolio: '投资组合', priority: '优先信号', top5: '重点关注 5 只', shortlist: '研究清单', noOrder: '不是买入指令',
    rank: '排名', symbol: '代码', confidence: '信心', currentMove: '当前变动', forecastTarget: '预测目标', livePrice: '实时价格', riskFlag: '风险提示',
    coverage: '覆盖范围', baseline: '基准价', movement: '变动', forecast: '预测', status: '状态', filterBy: '筛选条件', search: '搜索', allForecasts: '全部预测', allConfidence: '全部信心', allStatuses: '全部状态', high: '高', medium: '中', low: '低', highConfidence: '高信心', mediumConfidence: '中信心', lowConfidence: '低信心', resetFilters: '重置筛选',
    onTrack: '方向一致', counter: '方向相反', inRange: '范围内', watching: '观察中', unavailable: '不可用', pending: '等待中',
    benchmark: '基准', signalMix: '信号分布', verification: '验证', readOnlyContext: '只读信息',
    liveIndependent: '预测是保存的快照。实时价格独立来自 Yahoo Finance。',
    moveTip: '实时价格相对于保存的预测基准价的变动。', targetTip: '到下一个检查点的预期百分比变动。不是价格。',
    riskTip: '提示涨幅过大、波动、流动性或数据风险。不是买卖建议。', confidenceTip: '启发式信心。不是校准概率。', forecastTip: '下一个检查点的 UP、FLAT 或 DOWN 情景。不是保证。',
    method: '排名方式', lang: '语言', source: '来源', liveQuotes: '实时价格', chartHint: '点击行打开图表', closeChart: '关闭图表',
    filteredCount: '个结果', rowsPerPage: '每页行数', previous: '上一页', next: '下一页', page: '第', pageOf: '页，共', pageSuffix: '页', pagination: '分页',
  },
}

function tr(language: Language, key: string) {
  return copy[language][key] || copy.EN[key] || key
}

function Tip({ language, label, textKey }: { language: Language; label: string; textKey: string }) {
  return <span className="tip-wrap"><span className="tip-label" tabIndex={0} title={tr(language, textKey)} aria-label={`${label}: ${tr(language, textKey)}`}>{label}<span className="tip-icon">?</span></span><span className="tip-popup" role="tooltip">{tr(language, textKey)}</span></span>
}

function localizedStatus(language: Language, label: string) {
  const keys: Record<string, string> = { 'On track': 'onTrack', Counter: 'counter', 'In range': 'inRange', Watching: 'watching', Unavailable: 'unavailable', Pending: 'pending' }
  return tr(language, keys[label] || label)
}

function formatPrice(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : `Rp ${money.format(value)}`
}

function formatPrecise(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : preciseNumber.format(value)
}

function formatRupiah(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : `Rp ${money.format(value)}`
}

function formatSignedRupiah(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value === 0) return 'Rp 0'
  return `${value > 0 ? '+' : '-'}Rp ${money.format(Math.abs(value))}`
}

function formatPercent(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : dateTime.format(parsed)
}

function directionClass(direction: Direction) {
  return direction.toLowerCase()
}

function movementClass(value: number | null) {
  return value === null ? 'muted' : value > 0.05 ? 'positive' : value < -0.05 ? 'negative' : 'neutral'
}

function statusFor(stock: ForecastStock, quote: Quote | undefined, live: number | null) {
  if (live === null) return { label: quote?.error ? 'Unavailable' : 'Pending', tone: 'muted' as const }
  const movement = ((live - stock.baseline) / stock.baseline) * 100
  if (stock.forecast === 'UP') {
    if (movement > 0.1) return { label: 'On track', tone: 'good' as const }
    if (movement < -0.1) return { label: 'Counter', tone: 'warn' as const }
  }
  if (stock.forecast === 'DOWN') {
    if (movement < -0.1) return { label: 'On track', tone: 'good' as const }
    if (movement > 0.1) return { label: 'Counter', tone: 'warn' as const }
  }
  return { label: stock.forecast === 'FLAT' ? 'In range' : 'Watching', tone: 'muted' as const }
}

function livePriceFor(quote: Quote | undefined) {
  return quote?.price !== undefined && Number.isFinite(quote.price) ? quote.price : null
}

const confidencePoints: Record<Confidence, number> = { high: 45, medium: 30, low: 15 }

function focusScore(stock: ForecastStock) {
  const targetPoints = Math.min(Math.max(stock.target_return_pct, 0) * 30, 100)
  const momentumPoints = Math.min(Math.max(stock.baseline_change_pct, 0) * 5, 25)
  const extensionPenalty = stock.baseline_change_pct > 4 ? (stock.baseline_change_pct - 4) * 10 : 0
  return confidencePoints[stock.confidence] + targetPoints + momentumPoints - extensionPenalty
}

function focusRisk(stock: ForecastStock) {
  if (stock.baseline_change_pct > 4) return { label: 'Extended', tone: 'warn' }
  if (stock.baseline_change_pct > 2) return { label: 'Watch', tone: 'warn' }
  return { label: 'Measured', tone: 'good' }
}

function SortButton({
  label, column, sort, onSort,
}: { label: string; column: SortKey; sort: { key: SortKey; direction: SortDirection }; onSort: (key: SortKey) => void }) {
  const active = sort.key === column
  return (
    <button className={`sort-button ${active ? 'active' : ''}`} onClick={() => onSort(column)} type="button">
      {label}<span>{active ? (sort.direction === 'asc' ? '↑' : '↓') : '↕'}</span>
    </button>
  )
}

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
  const [quoteState, setQuoteState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [quoteError, setQuoteError] = useState('')
  const [lastRefresh, setLastRefresh] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [direction, setDirection] = useState<FilterDirection>('ALL')
  const [confidence, setConfidence] = useState<FilterConfidence>('ALL')
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({ key: 'symbol', direction: 'asc' })
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(1)
  const [expandedChart, setExpandedChart] = useState<{ symbol: string; area: 'focus' | 'watchlist' } | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)

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
      const [watchlistPayload, portfolioPayload] = await Promise.all([
        fetchQuotes('/api/quotes'),
        fetchQuotes(`/api/quotes?symbols=${portfolioSymbols.join(',')}`),
      ])
      const payloads = [watchlistPayload, portfolioPayload]
      const allQuotes = payloads.flatMap((payload) => payload.quotes)
      const mergedQuotes = Object.fromEntries(allQuotes.map((quote) => [quote.symbol, quote]))
      const pricedQuotes = allQuotes.filter((quote) => quote.price !== undefined && Number.isFinite(quote.price))
      const unavailableCount = allQuotes.length - pricedQuotes.length
      setQuotes(mergedQuotes)
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
      setData(payload)
      setError('')
      setLoading(false)
      void refreshQuotes()
    } catch (caught) {
      setLoading(false)
      setError(caught instanceof Error ? caught.message : 'Forecast load failed')
    }
  }, [refreshQuotes])

  useEffect(() => {
    window.localStorage.setItem('stock-dashboard-language', language)
  }, [language])

  useEffect(() => {
    void loadDashboard()
    const interval = window.setInterval(() => void refreshQuotes(), 60000)
    return () => window.clearInterval(interval)
  }, [loadDashboard, refreshQuotes])

  const rows = useMemo<Row[]>(() => {
    if (!data) return []
    return data.forecast.stocks.map((stock) => {
      const quote = quotes[stock.symbol]
      const live = livePriceFor(quote)
      const movement = live === null ? null : ((live - stock.baseline) / stock.baseline) * 100
      return { stock, quote, live, movement, status: statusFor(stock, quote, live) }
    })
  }, [data, quotes])

  const focusRows = useMemo<FocusRow[]>(() => rows
    .filter(({ stock }) => stock.forecast === 'UP')
    .map((row) => ({ ...row, score: focusScore(row.stock) }))
    .sort((left, right) => right.score - left.score || right.stock.target_return_pct - left.stock.target_return_pct || left.stock.symbol.localeCompare(right.stock.symbol))
    .slice(0, 5), [rows])

  const portfolioRows = useMemo<PortfolioRow[]>(() => portfolioPositions.map((position) => {
    const quote = quotes[position.symbol]
    const live = livePriceFor(quote)
    const shares = position.lots * LOT_SIZE
    const currentValue = live === null ? null : live * shares
    const pnl = currentValue === null ? null : currentValue - position.invested
    const pnlPct = pnl === null ? null : (pnl / position.invested) * 100
    return { ...position, quote, shares, live, currentValue, pnl, pnlPct, weight: null }
  }), [quotes])

  const portfolioCurrentValue = useMemo(() => {
    if (portfolioRows.some((row) => row.currentValue === null)) return null
    return portfolioRows.reduce((total, row) => total + (row.currentValue || 0), 0)
  }, [portfolioRows])

  const portfolioRowsWithWeight = useMemo(() => portfolioRows.map((row) => ({
    ...row,
    weight: portfolioCurrentValue === null || row.currentValue === null || portfolioCurrentValue === 0
      ? null
      : (row.currentValue / portfolioCurrentValue) * 100,
  })), [portfolioCurrentValue, portfolioRows])

  const investedTotal = portfolioPositions.reduce((total, position) => total + position.invested, 0)
  const portfolioPnl = portfolioCurrentValue === null ? null : portfolioCurrentValue - investedTotal
  const portfolioPnlPct = portfolioPnl === null ? null : (portfolioPnl / investedTotal) * 100

  const visibleRows = useMemo(() => {
    const search = query.trim().toUpperCase()
    const confidenceRank = { low: 1, medium: 2, high: 3 }
    const filtered = rows.filter(({ stock, status: rowStatus }) => (
      (!search || stock.symbol.includes(search)) &&
      (direction === 'ALL' || stock.forecast === direction) &&
      (confidence === 'ALL' || stock.confidence === confidence) &&
      (status === 'ALL' || rowStatus.label === status)
    ))
    return filtered.sort((a, b) => {
      const value = (row: Row): string | number => ({
        symbol: row.stock.symbol,
        baseline: row.stock.baseline,
        live: row.live ?? -Infinity,
        movement: row.movement ?? -Infinity,
        forecast: { UP: 3, FLAT: 2, DOWN: 1 }[row.stock.forecast],
        confidence: confidenceRank[row.stock.confidence],
        status: row.status.label,
      }[sort.key])
      const left = value(a)
      const right = value(b)
      const compared = typeof left === 'string' && typeof right === 'string'
        ? left.localeCompare(right)
        : Number(left) - Number(right)
      return sort.direction === 'asc' ? compared : -compared
    })
  }, [confidence, direction, query, rows, sort, status])

  const pageCount = Math.max(1, Math.ceil(visibleRows.length / pageSize))
  const paginatedRows = useMemo(() => {
    const start = (page - 1) * pageSize
    return visibleRows.slice(start, start + pageSize)
  }, [page, pageSize, visibleRows])

  useEffect(() => {
    setPage(1)
  }, [confidence, direction, pageSize, query, sort.direction, sort.key, status])

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount))
  }, [pageCount])

  useEffect(() => {
    if (expandedChart?.area === 'watchlist' && !paginatedRows.some((row) => row.stock.symbol === expandedChart.symbol)) {
      setExpandedChart(null)
    }
  }, [expandedChart, paginatedRows])

  const counts = useMemo(() => rows.reduce((result, row) => {
    result[row.stock.forecast] += 1
    return result
  }, { UP: 0, FLAT: 0, DOWN: 0 }), [rows])

  const changeSort = (key: SortKey) => {
    setSort((current) => current.key === key
      ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
      : { key, direction: key === 'symbol' ? 'asc' : 'desc' })
  }

  const toggleChart = (symbol: string, area: 'focus' | 'watchlist') => {
    setSelectedSymbol(symbol)
    setExpandedChart((current) => current?.symbol === symbol && current.area === area ? null : { symbol, area })
  }

  const chartKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, symbol: string, area: 'focus' | 'watchlist') => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleChart(symbol, area)
    }
  }

  if (loading && !data) return <main className="app-shell centered"><div className="loading-state"><span className="spinner" />Loading forecast universe…</div></main>
  if (error && !data) return <main className="app-shell centered"><div className="error-panel"><span className="error-icon">!</span><h1>Data source unavailable</h1><p>{error}</p><button className="button" onClick={() => void loadDashboard()} type="button">Try again</button></div></main>
  if (!data) return null

  const { forecast, verification } = data
  const accuracy = verification?.metrics.accuracy
  const evaluated = verification?.metrics.evaluated
  const benchmark = forecast.benchmark

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><span>↗</span></div>
          <div><div className="eyebrow">HERMES / {tr(language, 'market')}</div><h1>Stock analytics</h1></div>
        </div>
        <div className="topbar-right">
          <label className="language-picker"><span>{tr(language, 'lang')}</span><select aria-label={tr(language, 'lang')} value={language} onChange={(event) => setLanguage(event.target.value as Language)}>{(['EN', 'ID', 'MY', 'CN'] as Language[]).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <div className="read-only"><span className="live-dot" />{tr(language, 'readOnly')}</div>
          <button className="refresh-button" onClick={() => void refreshQuotes()} disabled={quoteState === 'loading'} type="button">
            <span className={quoteState === 'loading' ? 'spinner small' : ''}>{quoteState === 'loading' ? '' : '↻'}</span>
            {quoteState === 'loading' ? tr(language, 'refreshing') : tr(language, 'refresh')}
          </button>
        </div>
      </header>

      <section className="intro-row">
        <div>
          <div className="eyebrow accent">{view === 'watchlist' ? tr(language, 'watchPulse') : tr(language, 'portfolioView')} <span className="divider">/</span> {formatDate(forecast.as_of)} UTC+7</div>
          <h2>{view === 'watchlist' ? tr(language, 'signals') : tr(language, 'positions')}</h2>
          <p>{view === 'watchlist' ? tr(language, 'watchDesc') : tr(language, 'portfolioDesc')}</p>
        </div>
        <div className="intro-meta"><span>{forecast.universe_count} symbols</span><span>Threshold ±{forecast.actual_threshold_pct.toFixed(2)}%</span></div>
      </section>

      <section className="view-toolbar" aria-label="Dashboard views">
        <div><div className="section-kicker">{tr(language, 'workspace')}</div><span className="subtle">{tr(language, 'switchHelp')}</span></div>
        <div className="view-switch" role="tablist" aria-label="Dashboard view">
          <button aria-selected={view === 'watchlist'} className={view === 'watchlist' ? 'selected' : ''} onClick={() => setView('watchlist')} role="tab" type="button">{tr(language, 'watchlist')}</button>
          <button aria-selected={view === 'portfolio'} className={view === 'portfolio' ? 'selected' : ''} onClick={() => setView('portfolio')} role="tab" type="button">{tr(language, 'portfolio')}</button>
        </div>
      </section>

      <div className="workspace-layout">
        <div className="primary-column">
          {view === 'watchlist' ? <>
            <section className="focus-section" aria-labelledby="focus-title">
              <div className="focus-header">
                <div><div className="section-kicker amber-text">{tr(language, 'priority')}</div><h3 id="focus-title">{tr(language, 'top5')}</h3><p>{tr(language, 'shortlist')} · heuristic ranking</p></div>
                <span className="focus-note">{tr(language, 'noOrder')} / no guarantee</span>
              </div>
              <div className="signal-legend"><Tip language={language} label={tr(language, 'currentMove')} textKey="moveTip" /><Tip language={language} label={tr(language, 'forecastTarget')} textKey="targetTip" /><Tip language={language} label={tr(language, 'riskFlag')} textKey="riskTip" /><Tip language={language} label={tr(language, 'confidence')} textKey="confidenceTip" /><Tip language={language} label={tr(language, 'forecast')} textKey="forecastTip" /></div>
              <div className="table-wrap">
                <table className="focus-table">
                  <colgroup><col className="col-rank" /><col className="col-symbol" /><col className="col-confidence" /><col className="col-number" /><col className="col-number" /><col className="col-live" /><col className="col-risk" /></colgroup>
                  <thead><tr><th>{tr(language, 'rank')}</th><th>{tr(language, 'symbol')}</th><th><Tip language={language} label={tr(language, 'confidence')} textKey="confidenceTip" /></th><th className="numeric-heading"><Tip language={language} label={tr(language, 'currentMove')} textKey="moveTip" /></th><th className="numeric-heading"><Tip language={language} label={tr(language, 'forecastTarget')} textKey="targetTip" /></th><th className="numeric-heading">{tr(language, 'livePrice')}</th><th><Tip language={language} label={tr(language, 'riskFlag')} textKey="riskTip" /></th></tr></thead>
                  <tbody>{focusRows.map(({ stock, quote, live, movement }, index) => {
                    const risk = focusRisk(stock)
                    const isExpanded = expandedChart?.symbol === stock.symbol && expandedChart.area === 'focus'
                    return <Fragment key={stock.symbol}>
                    <tr className={`expandable-row ${isExpanded ? 'expanded' : ''}`} aria-label={`${stock.symbol}: ${tr(language, 'chartHint')}`} title={tr(language, 'chartHint')} aria-expanded={isExpanded} tabIndex={0} onClick={() => toggleChart(stock.symbol, 'focus')} onKeyDown={(event) => chartKeyDown(event, stock.symbol, 'focus')}>
                      <td className="rank">{index + 1}</td>
                      <td><span className="symbol">{stock.symbol}</span><span className="exchange">.JK</span></td>
                      <td><span className={`confidence ${stock.confidence}`}><i />{stock.confidence}</span></td>
                      <td className={`numeric ${movementClass(movement)}`}>{formatPercent(movement ?? stock.baseline_change_pct)}</td>
                      <td className="numeric target-value">{formatPercent(stock.target_return_pct, 1)}</td>
                      <td className="numeric live-price">{formatPrice(live)}</td>
                      <td><span className={`risk-label ${risk.tone}`}>{risk.label}</span></td>
                    </tr>
                    {isExpanded && <tr className="chart-detail-row" key={`${stock.symbol}-focus-chart`}><td colSpan={7}><StockChart language={language} symbol={stock.symbol} forecast={stock} quote={quote} /></td></tr>}
                    </Fragment>
                  })}</tbody>
                </table>
                {!focusRows.length && <div className="empty-state">No UP signals are available for the focus shortlist.</div>}
              </div>
            </section>
            {selectedSymbol && <ResearchPanel symbol={selectedSymbol} language={language} />}

            <details className="methodology-details">
              <summary>How the ranking works</summary>
              <div className="methodology-body">
                <p>UP signals are scored with confidence points (high 45, medium 30, low 15), target return × 30 capped at 100 points, and baseline change × 5 capped at 25 points. Moves above 4% receive an extension penalty.</p>
                <p className="methodology-disclaimer">Heuristic only. It is not a trained ML model, calibrated probability, or guarantee.</p>
                <div className="methodology-factors" aria-label="Heuristic inputs"><span>Intraday momentum</span><span>IHSG relative strength</span><span>Support / resistance</span><span>Sector &amp; news</span><span>Liquidity / data quality</span></div>
              </div>
            </details>

            <section className="watchlist-section">
              <div className="watchlist-header">
                <div><div className="section-kicker">{tr(language, 'coverage')}</div><h3>{tr(language, 'watchlist')}</h3><span className="subtle">{visibleRows.length} of {forecast.universe_count} symbols</span></div>
                <QuoteStatus language={language} quoteState={quoteState} lastRefresh={lastRefresh} quoteError={quoteError} />
              </div>
              <div className="controls" aria-label={tr(language, 'filterBy')}>
                <div className="filter-bar-title">{tr(language, 'filterBy')}</div>
                <label className="filter-field filter-search"><span>{tr(language, 'search')}</span><span className="search-box"><span aria-hidden="true">⌕</span><input aria-label={tr(language, 'search')} onChange={(event) => setQuery(event.target.value)} placeholder={`${tr(language, 'symbol')}...`} value={query} /></span></label>
                <label className="filter-field"><span>{tr(language, 'forecast')}</span><select aria-label={tr(language, 'forecast')} onChange={(event) => setDirection(event.target.value as FilterDirection)} value={direction}>
                  <option value="ALL">{tr(language, 'allForecasts')}</option><option value="UP">UP</option><option value="FLAT">FLAT</option><option value="DOWN">DOWN</option>
                </select></label>
                <label className="filter-field"><span>{tr(language, 'confidence')}</span><select aria-label={tr(language, 'confidence')} onChange={(event) => setConfidence(event.target.value as FilterConfidence)} value={confidence}>
                  <option value="ALL">{tr(language, 'allConfidence')}</option><option value="high">{tr(language, 'high')}</option><option value="medium">{tr(language, 'medium')}</option><option value="low">{tr(language, 'low')}</option>
                </select></label>
                <label className="filter-field"><span>{tr(language, 'status')}</span><select aria-label={tr(language, 'status')} onChange={(event) => setStatus(event.target.value as StatusFilter)} value={status}>
                  <option value="ALL">{tr(language, 'allStatuses')}</option>
                  {(['On track', 'Counter', 'In range', 'Watching', 'Unavailable', 'Pending'] as Exclude<StatusFilter, 'ALL'>[]).map((item) => <option key={item} value={item}>{localizedStatus(language, item)}</option>)}
                </select></label>
                {(Boolean(query.trim()) || direction !== 'ALL' || confidence !== 'ALL' || status !== 'ALL') && <button className="reset-filters" onClick={() => { setQuery(''); setDirection('ALL'); setConfidence('ALL'); setStatus('ALL') }} type="button">{tr(language, 'resetFilters')}</button>}
              </div>
              <div className="pagination-toolbar" aria-label={`${tr(language, 'watchlist')} ${tr(language, 'pagination')}`}>
                <span className="pagination-count">{visibleRows.length} {tr(language, 'filteredCount')}</span>
                <div className="pagination-controls">
                  <label className="pagination-size"><span>{tr(language, 'rowsPerPage')}</span><select aria-label={tr(language, 'rowsPerPage')} value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option></select></label>
                  <button className="pagination-button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} type="button">{tr(language, 'previous')}</button>
                  <span className="pagination-indicator" aria-live="polite">{tr(language, 'page')} {page} {tr(language, 'pageOf')} {pageCount} {tr(language, 'pageSuffix')}</span>
                  <button className="pagination-button" disabled={page >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))} type="button">{tr(language, 'next')}</button>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead><tr>
                    <th><SortButton column="symbol" label={tr(language, 'symbol')} onSort={changeSort} sort={sort} /></th>
                    <th className="numeric-heading"><SortButton column="baseline" label={tr(language, 'baseline')} onSort={changeSort} sort={sort} /></th>
                    <th className="numeric-heading"><SortButton column="live" label={tr(language, 'livePrice')} onSort={changeSort} sort={sort} /></th>
                    <th className="numeric-heading"><SortButton column="movement" label={tr(language, 'movement')} onSort={changeSort} sort={sort} /></th>
                    <th><SortButton column="forecast" label={tr(language, 'forecast')} onSort={changeSort} sort={sort} /></th>
                    <th><SortButton column="confidence" label={tr(language, 'confidence')} onSort={changeSort} sort={sort} /></th>
                    <th><SortButton column="status" label={tr(language, 'status')} onSort={changeSort} sort={sort} /></th>
                  </tr></thead>
                  <tbody>{paginatedRows.map(({ stock, quote, live, movement, status }) => {
                    const isExpanded = expandedChart?.symbol === stock.symbol && expandedChart.area === 'watchlist'
                    return <Fragment key={stock.symbol}>
                      <tr className={`expandable-row ${isExpanded ? 'expanded' : ''}`} aria-label={`${stock.symbol}: ${tr(language, 'chartHint')}`} title={tr(language, 'chartHint')} aria-expanded={isExpanded} tabIndex={0} onClick={() => toggleChart(stock.symbol, 'watchlist')} onKeyDown={(event) => chartKeyDown(event, stock.symbol, 'watchlist')}>
                        <td><span className="symbol">{stock.symbol}</span><span className="exchange">.JK</span></td>
                        <td className="numeric">{formatPrice(stock.baseline)}</td>
                        <td className="numeric live-price">{formatPrice(live)}</td>
                        <td className={`numeric ${movementClass(movement)}`}>{formatPercent(movement)}</td>
                        <td><span className={`forecast-badge ${directionClass(stock.forecast)}`}><span>{stock.forecast === 'UP' ? '↗' : stock.forecast === 'DOWN' ? '↘' : '→'}</span>{stock.forecast}</span><span className="target">{formatPercent(stock.target_return_pct, 1)} target</span></td>
                        <td><span className={`confidence ${stock.confidence}`}><i />{stock.confidence}</span></td>
                        <td><span className={`status-pill ${status.tone}`}>{localizedStatus(language, status.label)}</span>{quote?.error && <span className="row-error" title={quote.error}>!</span>}</td>
                      </tr>
                      {isExpanded && <tr className="chart-detail-row" key={`${stock.symbol}-watchlist-chart`}><td colSpan={7}><StockChart language={language} symbol={stock.symbol} forecast={stock} quote={quote} /></td></tr>}
                    </Fragment>
                  })}</tbody>
                </table>
                {!visibleRows.length && <div className="empty-state">No symbols match the current filters.</div>}
              </div>
            </section>
          </> : <PortfolioView language={language} rows={portfolioRowsWithWeight} currentValue={portfolioCurrentValue} investedTotal={investedTotal} pnl={portfolioPnl} pnlPct={portfolioPnlPct} quoteState={quoteState} lastRefresh={lastRefresh} quoteError={quoteError} />}
        </div>

        <aside className="context-column" aria-label="Market context">
            <section className="context-block benchmark-block">
            <div className="section-kicker">{tr(language, 'benchmark')} / {benchmark.symbol}</div>
            <div className="benchmark-value">{formatPrice(benchmark.displayed_price)}</div>
            <div className="positive">{formatPercent(benchmark.displayed_change_pct)} today</div>
            <span className="context-note">Forecast threshold ±{forecast.actual_threshold_pct.toFixed(2)}%</span>
          </section>
          {view === 'watchlist' && <>
            <section className="context-block">
              <div className="section-kicker">SIGNAL MIX</div>
              <div className="signal-counts"><span className="positive"><strong>{counts.UP}</strong> UP</span><span className="neutral"><strong>{counts.FLAT}</strong> FLAT</span><span className="negative"><strong>{counts.DOWN}</strong> DOWN</span></div>
            </section>
            <section className="context-block">
              <div className="section-kicker">VERIFICATION</div>
              <div className="context-value">{accuracy === null || accuracy === undefined ? 'Pending' : `${accuracy.toFixed(1)}%`}</div>
              <span className="context-note">{verification ? `${evaluated ?? '—'} observations scored` : 'Mount report to score forecasts'}</span>
            </section>
          </>}
          <section className="context-block context-footnote">
            <div className="section-kicker">READ-ONLY CONTEXT</div>
            <p>Forecasts are saved snapshots. Live prices refresh independently from Yahoo Finance.</p>
            <span className="context-note">As of {formatDate(forecast.as_of)} UTC+7</span>
          </section>
        </aside>
      </div>

      <footer><span>Source · {forecast.source}</span><span>{verification ? `Verification · ${verification.format} report mounted` : 'Verification · report not mounted'}</span><span>Live quotes · Yahoo Finance chart API</span></footer>
    </main>
  )
}

function QuoteStatus({
  language, quoteState, lastRefresh, quoteError,
}: { language: Language; quoteState: 'idle' | 'loading' | 'ready' | 'error'; lastRefresh: string | null; quoteError: string }) {
  return (
    <div className="quote-status">
      <span className={`status-dot ${quoteState === 'ready' ? 'green' : quoteState === 'error' ? 'amber' : ''}`} />
      <span>{quoteState === 'ready' ? `${tr(language, 'liveQuotes')} · ${formatDate(lastRefresh)}` : quoteState === 'loading' ? `${tr(language, 'liveQuotes')}...` : quoteError || tr(language, 'pending')}</span>
    </div>
  )
}

function PortfolioView({
  language, rows, currentValue, investedTotal, pnl, pnlPct, quoteState, lastRefresh, quoteError,
}: {
  language: Language
  rows: PortfolioRow[]
  currentValue: number | null
  investedTotal: number
  pnl: number | null
  pnlPct: number | null
  quoteState: 'idle' | 'loading' | 'ready' | 'error'
  lastRefresh: string | null
  quoteError: string
}) {
  const pricedCount = rows.filter((row) => row.live !== null).length
  const pnlTone = pnl === null ? 'muted' : pnl >= 0 ? 'positive' : 'negative'

  return (
    <section className="watchlist-card portfolio-card">
      <div className="watchlist-header">
        <div><div className="section-kicker">{tr(language, 'portfolioView')}</div><h3>{tr(language, 'portfolio')}</h3><span className="subtle">{rows.length} positions · exact saved cost basis</span></div>
        <QuoteStatus language={language} quoteState={quoteState} lastRefresh={lastRefresh} quoteError={quoteError} />
      </div>

      <div className="portfolio-summary" aria-label="Portfolio summary">
        <div className="portfolio-summary-card"><div className="card-heading"><span>INVESTED CAPITAL</span><span className="card-icon">⌁</span></div><div className="portfolio-summary-value">{formatRupiah(investedTotal)}</div><div className="card-foot">Saved cost basis</div></div>
        <div className="portfolio-summary-card"><div className="card-heading"><span>CURRENT VALUE</span><span className="card-icon">◉</span></div><div className="portfolio-summary-value">{formatRupiah(currentValue)}</div><div className="card-foot">{currentValue === null ? `${pricedCount} of ${rows.length} quotes available` : 'Marked to live quotes'}</div></div>
        <div className="portfolio-summary-card"><div className="card-heading"><span>UNREALIZED P/L</span><span className={`card-icon ${pnlTone}`}>↕</span></div><div className={`portfolio-summary-value ${pnlTone}`}>{formatSignedRupiah(pnl)}</div><div className="card-foot">{pnl === null ? 'Waiting for all position quotes' : 'Current value less invested'}</div></div>
        <div className="portfolio-summary-card"><div className="card-heading"><span>PORTFOLIO RETURN</span><span className={`card-icon ${pnlTone}`}>%</span></div><div className={`portfolio-summary-value ${pnlTone}`}>{formatPercent(pnlPct)}</div><div className="card-foot">Unrealized P/L percentage</div></div>
      </div>

      <div className="portfolio-note"><span>Weight is calculated from total current value when all four live quotes are available.</span><span>Lots × {LOT_SIZE} shares</span></div>

      <div className="table-wrap">
        <table className="portfolio-table">
          <thead><tr>
            <th>Symbol</th><th className="numeric-heading">Lots</th><th className="numeric-heading">Shares</th><th className="numeric-heading">Avg cost</th><th className="numeric-heading">Invested</th><th className="numeric-heading">Live price</th><th className="numeric-heading">Current value</th><th className="numeric-heading">Unrealized P/L</th><th className="numeric-heading">P/L %</th><th className="numeric-heading">Weight</th>
          </tr></thead>
          <tbody>{rows.map((row) => <tr key={row.symbol}>
            <td><span className="symbol">{row.symbol}</span><span className="exchange">.JK</span>{row.quote?.error && <span className="row-error" title={row.quote.error}>!</span>}</td>
            <td className="numeric">{formatPrecise(row.lots)}</td>
            <td className="numeric">{money.format(row.shares)}</td>
            <td className="numeric">{formatPrecise(row.averageCost)}</td>
            <td className="numeric">{formatRupiah(row.invested)}</td>
            <td className="numeric live-price">{formatPrice(row.live)}</td>
            <td className="numeric">{formatRupiah(row.currentValue)}</td>
            <td className={`numeric ${pnlToneFor(row.pnl)}`}>{formatSignedRupiah(row.pnl)}</td>
            <td className={`numeric ${pnlToneFor(row.pnl)}`}>{formatPercent(row.pnlPct)}</td>
            <td className="numeric">{formatPercent(row.weight, 1)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  )
}

function pnlToneFor(value: number | null) {
  return value === null ? 'muted' : value >= 0 ? 'positive' : 'negative'
}

function SummaryCard({ label, value, note, tone }: { label: Direction; value: number; note: string; tone: string }) {
  return <div className={`summary-card ${tone}`}><div className="card-heading"><span>{label}</span><span className="card-icon">{label === 'UP' ? '↗' : label === 'DOWN' ? '↘' : '→'}</span></div><div className="summary-value">{value}</div><div className="card-foot">{note}</div></div>
}

export default App

createRoot(document.getElementById('root')!).render(<App />)
