import type { Confidence, ForecastStock, Quote } from './types'

export const LOT_SIZE = 100
export const portfolioPositions = [
  { symbol: 'BBCA', lots: 9, averageCost: 6009, invested: 5408100 },
  { symbol: 'BNBR', lots: 166.96, averageCost: 156.34, invested: 2610289 },
  { symbol: 'ELTY', lots: 125, averageCost: 43.96, invested: 549623 },
  { symbol: 'PRDL', lots: 1, averageCost: 120, invested: 12000 },
]
export const portfolioSymbols = portfolioPositions.map(({ symbol }) => symbol)
export const money = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const preciseNumber = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const dateTime = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })

export const formatPrice = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : `Rp ${money.format(value)}`
export const formatPrecise = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : preciseNumber.format(value)
export const formatRupiah = formatPrice
export function formatSignedRupiah(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  if (value === 0) return 'Rp 0'
  return `${value > 0 ? '+' : '-'}Rp ${money.format(Math.abs(value))}`
}
export function formatPercent(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`
}
export function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : dateTime.format(parsed)
}
export const movementClass = (value: number | null) => value === null ? 'muted' : value > 0.05 ? 'positive' : value < -0.05 ? 'negative' : 'neutral'
export const livePriceFor = (quote: Quote | undefined) => quote?.price !== undefined && Number.isFinite(quote.price) ? quote.price : null
export function statusFor(stock: ForecastStock, quote: Quote | undefined, live: number | null) {
  if (live === null) return { label: quote?.error ? 'Unavailable' : 'Pending', tone: 'muted' as const }
  const movement = ((live - stock.baseline) / stock.baseline) * 100
  if (stock.forecast === 'UP' && movement > 0.1 || stock.forecast === 'DOWN' && movement < -0.1) return { label: 'On track', tone: 'good' as const }
  if (stock.forecast === 'UP' && movement < -0.1 || stock.forecast === 'DOWN' && movement > 0.1) return { label: 'Counter', tone: 'warn' as const }
  return { label: stock.forecast === 'FLAT' ? 'In range' : 'Watching', tone: 'muted' as const }
}
const confidencePoints: Record<Confidence, number> = { high: 45, medium: 30, low: 15 }
export function focusScore(stock: ForecastStock) {
  return confidencePoints[stock.confidence] + Math.min(Math.max(stock.target_return_pct, 0) * 30, 100) + Math.min(Math.max(stock.baseline_change_pct, 0) * 5, 25) - (stock.baseline_change_pct > 4 ? (stock.baseline_change_pct - 4) * 10 : 0)
}
export function focusRisk(stock: ForecastStock) {
  if (stock.baseline_change_pct > 4) return { label: 'Extended', tone: 'warn' }
  if (stock.baseline_change_pct > 2) return { label: 'Watch', tone: 'warn' }
  return { label: 'Measured', tone: 'good' }
}
export const pnlToneFor = (value: number | null) => value === null ? 'muted' : value >= 0 ? 'positive' : 'negative'
