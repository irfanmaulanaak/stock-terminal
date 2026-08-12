import { tr } from '../i18n'
import type { AuditPayload, Language, MethodologyPayload, VerificationMetrics } from '../types'

interface Props { language: Language; audit: AuditPayload | null; methodology: MethodologyPayload | null; loading: boolean; error: string }

const metric = (value: number | null | undefined, suffix = '%') => value == null ? '—' : `${value.toFixed(2)}${suffix}`
const text = (value: string | null | undefined) => value || '—'

function Metrics({ metrics }: { metrics: VerificationMetrics | null | undefined }) {
  const values = [
    ['Accuracy', metric(metrics?.accuracy)], ['Balanced accuracy', metric(metrics?.balancedAccuracy)], ['Macro-F1', metric(metrics?.macroF1)],
    ['MAE', metric(metrics?.mae, ' pp')], ['Brier', metric(metrics?.brier, '')], ['ECE', metric(metrics?.ece, '')], ['Coverage', metric(metrics?.coverage)],
  ]
  return <div className="audit-metrics">{values.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
}

export function TransparencyPanel({ language, audit, methodology, loading, error }: Props) {
  if (loading) return <section className="transparency-panel transparency-state"><span className="spinner" />{tr(language, 'auditLoading')}</section>
  if (error) return <section className="transparency-panel transparency-state negative">{tr(language, 'auditError')}: {error}</section>
  const forecast = audit?.forecast
  const confidence = forecast?.stocks.reduce<Record<string, number>>((result, stock) => { const key = stock.confidence || 'unavailable'; result[key] = (result[key] || 0) + 1; return result }, {}) || {}
  const modifiers = forecast?.stocks.reduce<Record<string, number>>((result, stock) => { const key = stock.modifier || 'unavailable'; result[key] = (result[key] || 0) + 1; return result }, {}) || {}
  const probabilityCount = forecast?.stocks.filter((stock) => stock.probabilities && Object.values(stock.probabilities).every((value) => value != null)).length || 0
  const verification = audit?.verification
  return <section className="transparency-panel" aria-label={tr(language, 'forecastAudit')}>
    <div className="transparency-header"><div><div className="section-kicker">{tr(language, 'transparency')}</div><h3>{tr(language, 'forecastAudit')}</h3></div><span className={`audit-status ${audit?.status === 'available' ? 'good' : 'warn'}`}>{tr(language, audit?.status === 'available' ? 'available' : 'unavailable')}</span></div>
    <div className="transparency-grid">
      <article className="audit-card"><h4>{tr(language, 'forecastMetadata')}</h4><dl><div><dt>{tr(language, 'asOf')}</dt><dd>{text(forecast?.asOf)}</dd></div><div><dt>{tr(language, 'horizon')}</dt><dd>{text(forecast?.horizon)}</dd></div><div><dt>{tr(language, 'modelVersion')}</dt><dd>{text(forecast?.modelVersion)}</dd></div><div><dt>{tr(language, 'confidence')}</dt><dd>{Object.entries(confidence).map(([key, value]) => `${key} ${value}`).join(' · ') || '—'}</dd></div><div><dt>{tr(language, 'probability')}</dt><dd>{probabilityCount ? `${probabilityCount}/${forecast?.stocks.length}` : tr(language, 'notPublished')}</dd></div><div><dt>{tr(language, 'modifier')}</dt><dd>{Object.entries(modifiers).map(([key, value]) => `${key} ${value}`).join(' · ') || '—'}</dd></div><div><dt>{tr(language, 'freshness')}</dt><dd>{forecast?.dataQuality.maxQuoteAgeSeconds == null ? '—' : `${forecast.dataQuality.minQuoteAgeSeconds}–${forecast.dataQuality.maxQuoteAgeSeconds}s · ${forecast.dataQuality.staleSymbolCount} ${tr(language, 'stale')}`}</dd></div><div><dt>{tr(language, 'dataQuality')}</dt><dd>{text(forecast?.dataQuality.status)}</dd></div></dl></article>
      <article className="audit-card"><h4>{tr(language, 'verificationMetrics')}</h4><Metrics metrics={verification?.metrics} /><p className="audit-note">{verification?.message || `${verification?.metrics.evaluated ?? '—'} ${tr(language, 'observationsScored')}`}</p></article>
      <article className="audit-card methodology-card"><h4>{tr(language, 'methodologyLimitations')}</h4><p>{methodology?.dataSeparationPolicy || '—'}</p><p>{methodology?.staleDataCaveat || forecast?.dataQuality.caveat || '—'}</p><ul>{methodology?.checkpointHorizons.map((item) => <li key={item}>{item}</li>)}</ul><p className="disclaimer">{methodology?.disclaimer || tr(language, 'executionDisclaimer')}</p></article>
    </div>
  </section>
}
