export type Direction = 'UP' | 'FLAT' | 'DOWN'
export type Confidence = 'low' | 'medium' | 'high'
export type FilterDirection = Direction | 'ALL'
export type FilterConfidence = Confidence | 'ALL'
export type StatusFilter = 'ALL' | 'On track' | 'Counter' | 'In range' | 'Watching' | 'Unavailable' | 'Pending'
export type SortKey = 'symbol' | 'baseline' | 'live' | 'movement' | 'forecast' | 'confidence' | 'status'
export type SortDirection = 'asc' | 'desc'
export type DashboardView = 'watchlist' | 'portfolio'
export type Language = 'EN' | 'ID' | 'MY' | 'CN'
export type QuoteState = 'idle' | 'loading' | 'ready' | 'error'

export interface ForecastStock {
  symbol: string
  baseline: number
  baseline_change_pct: number
  forecast: Direction
  target_return_pct: number
  confidence: Confidence
}

export interface Forecast {
  as_of: string
  source: string
  actual_threshold_pct: number
  universe_count: number
  benchmark: { symbol: string; displayed_price: number; displayed_change_pct: number }
  stocks: ForecastStock[]
}

export interface Verification {
  path: string
  format: string
  metrics: { accuracy: number | null; directionalAccuracy: number | null; correct: number | null; evaluated: number | null }
}

export interface DashboardPayload { forecast: Forecast; verification: Verification | null }

export interface Quote {
  symbol: string
  yahooSymbol: string
  price?: number
  previousClose?: number | null
  change?: number | null
  changePct?: number | null
  asOf?: string | null
  error?: string
}

export interface QuotePayload { quotes: Quote[]; fetchedAt: string; source: string }

export interface Row {
  stock: ForecastStock
  quote?: Quote
  live: number | null
  movement: number | null
  status: { label: string; tone: 'good' | 'warn' | 'muted' }
}

export interface FocusRow extends Row { score: number }
export interface PortfolioPosition { symbol: string; lots: number; averageCost: number; invested: number }
export interface PortfolioRow extends PortfolioPosition {
  quote?: Quote
  shares: number
  live: number | null
  currentValue: number | null
  pnl: number | null
  pnlPct: number | null
  weight: number | null
}
