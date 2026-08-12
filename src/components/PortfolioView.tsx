import { QuoteStatus } from './QuoteStatus'
import { tr } from '../i18n'
import type { Language, PortfolioRow, QuoteState } from '../types'
import { LOT_SIZE, formatPercent, formatPrecise, formatPrice, formatRupiah, formatSignedRupiah, money, pnlToneFor } from '../utils'

interface Props { language: Language; rows: PortfolioRow[]; currentValue: number | null; investedTotal: number; pnl: number | null; pnlPct: number | null; quoteState: QuoteState; lastRefresh: string | null; quoteError: string }

export function PortfolioView({ language, rows, currentValue, investedTotal, pnl, pnlPct, quoteState, lastRefresh, quoteError }: Props) {
  const pricedCount = rows.filter((row) => row.live !== null).length
  const pnlTone = pnlToneFor(pnl)
  return <section className="watchlist-card portfolio-card">
    <div className="watchlist-header"><div><div className="section-kicker">{tr(language, 'portfolioView')}</div><h3>{tr(language, 'portfolio')}</h3><span className="subtle">{rows.length} positions · exact saved cost basis</span></div><QuoteStatus {...{ language, quoteState, lastRefresh, quoteError }} /></div>
    <div className="portfolio-summary" aria-label="Portfolio summary">
      <div className="portfolio-summary-card"><div className="card-heading"><span>INVESTED CAPITAL</span><span className="card-icon">⌁</span></div><div className="portfolio-summary-value">{formatRupiah(investedTotal)}</div><div className="card-foot">Saved cost basis</div></div>
      <div className="portfolio-summary-card"><div className="card-heading"><span>CURRENT VALUE</span><span className="card-icon">◉</span></div><div className="portfolio-summary-value">{formatRupiah(currentValue)}</div><div className="card-foot">{currentValue === null ? `${pricedCount} of ${rows.length} quotes available` : 'Marked to live quotes'}</div></div>
      <div className="portfolio-summary-card"><div className="card-heading"><span>UNREALIZED P/L</span><span className={`card-icon ${pnlTone}`}>↕</span></div><div className={`portfolio-summary-value ${pnlTone}`}>{formatSignedRupiah(pnl)}</div><div className="card-foot">{pnl === null ? 'Waiting for all position quotes' : 'Current value less invested'}</div></div>
      <div className="portfolio-summary-card"><div className="card-heading"><span>PORTFOLIO RETURN</span><span className={`card-icon ${pnlTone}`}>%</span></div><div className={`portfolio-summary-value ${pnlTone}`}>{formatPercent(pnlPct)}</div><div className="card-foot">Unrealized P/L percentage</div></div>
    </div>
    <div className="portfolio-note"><span>Weight is calculated from total current value when all four live quotes are available.</span><span>Lots × {LOT_SIZE} shares</span></div>
    <div className="table-wrap"><table className="portfolio-table"><thead><tr><th>Symbol</th><th className="numeric-heading">Lots</th><th className="numeric-heading">Shares</th><th className="numeric-heading">Avg cost</th><th className="numeric-heading">Invested</th><th className="numeric-heading">Live price</th><th className="numeric-heading">Current value</th><th className="numeric-heading">Unrealized P/L</th><th className="numeric-heading">P/L %</th><th className="numeric-heading">Weight</th></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.symbol}><td><span className="symbol">{row.symbol}</span><span className="exchange">.JK</span>{row.quote?.error && <span className="row-error" title={row.quote.error}>!</span>}</td><td className="numeric">{formatPrecise(row.lots)}</td><td className="numeric">{money.format(row.shares)}</td><td className="numeric">{formatPrecise(row.averageCost)}</td><td className="numeric">{formatRupiah(row.invested)}</td><td className="numeric live-price">{formatPrice(row.live)}</td><td className="numeric">{formatRupiah(row.currentValue)}</td><td className={`numeric ${pnlToneFor(row.pnl)}`}>{formatSignedRupiah(row.pnl)}</td><td className={`numeric ${pnlToneFor(row.pnl)}`}>{formatPercent(row.pnlPct)}</td><td className="numeric">{formatPercent(row.weight, 1)}</td></tr>)}</tbody>
    </table></div>
  </section>
}
