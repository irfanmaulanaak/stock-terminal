import { Fragment, type KeyboardEvent } from 'react'
import { ResearchPanel } from '../ResearchPanel'
import { StockChart } from '../StockChart'
import { tr } from '../i18n'
import type { FocusRow, Language } from '../types'
import { focusRisk, formatPercent, formatPrice, movementClass } from '../utils'
import { Tip } from './Tip'

interface Props { language: Language; rows: FocusRow[]; expanded: string | null; selectedSymbol: string | null; onToggle: (symbol: string) => void }

export function FocusSignals({ language, rows, expanded, selectedSymbol, onToggle }: Props) {
  const keyDown = (event: KeyboardEvent<HTMLTableRowElement>, symbol: string) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onToggle(symbol) }
  }
  return <>
    <section className="focus-section" aria-labelledby="focus-title">
      <div className="focus-header"><div><div className="section-kicker amber-text">{tr(language, 'priority')}</div><h3 id="focus-title">{tr(language, 'top5')}</h3><p>{tr(language, 'shortlist')} · heuristic ranking</p></div><span className="focus-note">{tr(language, 'noOrder')} / no guarantee</span></div>
      <div className="signal-legend"><Tip language={language} label={tr(language, 'currentMove')} textKey="moveTip" /><Tip language={language} label={tr(language, 'forecastTarget')} textKey="targetTip" /><Tip language={language} label={tr(language, 'riskFlag')} textKey="riskTip" /><Tip language={language} label={tr(language, 'confidence')} textKey="confidenceTip" /><Tip language={language} label={tr(language, 'forecast')} textKey="forecastTip" /></div>
      <div className="table-wrap"><table className="focus-table"><colgroup><col className="col-rank" /><col className="col-symbol" /><col className="col-confidence" /><col className="col-number" /><col className="col-number" /><col className="col-live" /><col className="col-risk" /></colgroup>
        <thead><tr><th>{tr(language, 'rank')}</th><th>{tr(language, 'symbol')}</th><th><Tip language={language} label={tr(language, 'confidence')} textKey="confidenceTip" /></th><th className="numeric-heading"><Tip language={language} label={tr(language, 'currentMove')} textKey="moveTip" /></th><th className="numeric-heading"><Tip language={language} label={tr(language, 'forecastTarget')} textKey="targetTip" /></th><th className="numeric-heading">{tr(language, 'livePrice')}</th><th><Tip language={language} label={tr(language, 'riskFlag')} textKey="riskTip" /></th></tr></thead>
        <tbody>{rows.map(({ stock, quote, live, movement }, index) => { const risk = focusRisk(stock); const isExpanded = expanded === stock.symbol; return <Fragment key={stock.symbol}><tr className={`expandable-row ${isExpanded ? 'expanded' : ''}`} aria-label={`${stock.symbol}: ${tr(language, 'chartHint')}`} title={tr(language, 'chartHint')} aria-expanded={isExpanded} tabIndex={0} onClick={() => onToggle(stock.symbol)} onKeyDown={(event) => keyDown(event, stock.symbol)}><td className="rank">{index + 1}</td><td><span className="symbol">{stock.symbol}</span><span className="exchange">.JK</span></td><td><span className={`confidence ${stock.confidence}`}><i />{stock.confidence}</span></td><td className={`numeric ${movementClass(movement)}`}>{formatPercent(movement ?? stock.baseline_change_pct)}</td><td className="numeric target-value">{formatPercent(stock.target_return_pct, 1)}</td><td className="numeric live-price">{formatPrice(live)}</td><td><span className={`risk-label ${risk.tone}`}>{risk.label}</span></td></tr>{isExpanded && <tr className="chart-detail-row"><td colSpan={7}><StockChart language={language} symbol={stock.symbol} forecast={stock} quote={quote} /></td></tr>}</Fragment> })}</tbody>
      </table>{!rows.length && <div className="empty-state">No UP signals are available for the focus shortlist.</div>}</div>
    </section>
    {selectedSymbol && <ResearchPanel symbol={selectedSymbol} language={language} />}
    <details className="methodology-details"><summary>How the ranking works</summary><div className="methodology-body"><p>UP signals are scored with confidence points (high 45, medium 30, low 15), target return × 30 capped at 100 points, and baseline change × 5 capped at 25 points. Moves above 4% receive an extension penalty.</p><p className="methodology-disclaimer">Heuristic only. It is not a trained ML model, calibrated probability, or guarantee.</p><div className="methodology-factors" aria-label="Heuristic inputs"><span>Intraday momentum</span><span>IHSG relative strength</span><span>Support / resistance</span><span>Sector &amp; news</span><span>Liquidity / data quality</span></div></div></details>
  </>
}
