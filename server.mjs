import { createServer } from 'node:http'
import { promises as fs } from 'node:fs'
import { extname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const appDir = resolve(fileURLToPath(new URL('.', import.meta.url)))
const distDir = join(appDir, 'dist')
const port = Number(process.env.PORT || 4173)
const host = process.env.HOST || '0.0.0.0'
const forecastPath = process.env.FORECAST_FILE || '/opt/data/watchlist_forecast_latest.json'
const verificationPaths = [
  process.env.VERIFICATION_FILE,
  '/opt/data/watchlist_verification_latest.md',
  '/opt/data/watchlist_verification_latest.json',
  '/opt/data/watchlist_verification_2026-08-12.md',
  '/opt/data/watchlist_verification_2026-08-12.json',
  '/opt/data/temp_watchlist_verification_2026-08-12.json',
].filter(Boolean)

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
}
const quoteCache = new Map()
const chartCache = new Map()
const researchCache = new Map()
const quoteSymbolPattern = /^[A-Z0-9]{1,6}(?:\.JK)?$/
const chartRanges = new Set(['1d', '5d', '1mo', '3mo', '1y'])
const chartIntervals = new Set(['5m', '15m', '1h', '1d'])
const maxQuoteSymbols = 100
const researchCacheMs = 5 * 60 * 1000
const researchUpstreamState = new Map()
const researchTimeoutMs = 7000
const researchMaxAttempts = 2

function sendJson(res, status, payload) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*',
  })
  res.end(JSON.stringify(payload))
}

async function readForecast() {
  const raw = await fs.readFile(forecastPath, 'utf8')
  return JSON.parse(raw)
}

function keyName(value) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function flatten(value, output = {}) {
  if (!value || typeof value !== 'object') return output
  for (const [key, child] of Object.entries(value)) {
    if (child !== null && typeof child === 'object') flatten(child, output)
    else output[keyName(key)] = child
  }
  return output
}

function numberFrom(flat, names) {
  for (const name of names) {
    const value = Number(flat[keyName(name)])
    if (Number.isFinite(value)) return value
  }
  return null
}

function percent(value) {
  if (value === null || !Number.isFinite(value)) return null
  return Math.abs(value) <= 1 ? value * 100 : value
}

function finiteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function stringValue(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function textPercent(raw, terms) {
  const match = raw.match(new RegExp(`(?:${terms})[^\\d%]{0,48}(\\d+(?:\\.\\d+)?)\\s*%?`, 'i'))
  return match ? percent(Number(match[1])) : null
}

function parseVerification(raw, path) {
  const isJson = extname(path).toLowerCase() === '.json'
  let flat = {}
  if (isJson) {
    try {
      flat = flatten(JSON.parse(raw))
    } catch {
      flat = {}
    }
  }

  let accuracy = numberFrom(flat, ['accuracy', 'overall_accuracy', 'overallAccuracy', 'hit_rate', 'hitRate'])
  let directionalAccuracy = numberFrom(flat, ['directional_accuracy', 'directionalAccuracy', 'direction_accuracy'])
  let correct = numberFrom(flat, ['correct', 'correct_predictions', 'correctPredictions', 'hits'])
  let evaluated = numberFrom(flat, ['evaluated', 'total', 'sample_count', 'sampleCount', 'n'])
  let balancedAccuracy = numberFrom(flat, ['balanced_accuracy_pct', 'balanced_accuracy', 'balancedAccuracy'])
  let macroF1 = numberFrom(flat, ['macro_f1_pct', 'macro_f1', 'macroF1'])
  let mae = numberFrom(flat, ['target_mae_pct', 'target_mae', 'mae', 'mean_absolute_error'])
  let brier = numberFrom(flat, ['brier_score', 'brier'])
  let ece = numberFrom(flat, ['expected_calibration_error', 'ece'])
  let coverage = numberFrom(flat, ['coverage_pct', 'coverage'])

  if (!isJson) {
    accuracy ??= textPercent(raw, 'overall accuracy|accuracy|hit rate|correctness')
    directionalAccuracy ??= textPercent(raw, 'directional accuracy|direction accuracy')
    balancedAccuracy ??= textPercent(raw, 'balanced accuracy')
    macroF1 ??= textPercent(raw, 'macro[ -]?f1')
    coverage ??= textPercent(raw, 'coverage')
    const maeMatch = raw.match(/(?:target(?:-return)?\s+mae|\bmae)[^\d]{0,32}(\d+(?:\.\d+)?)/i)
    mae ??= maeMatch ? Number(maeMatch[1]) : null
    const brierMatch = raw.match(/(?:brier(?: score)?)[^\d]{0,32}(0?\.\d+|\d+(?:\.\d+)?)/i)
    brier ??= brierMatch ? Number(brierMatch[1]) : null
    const eceMatch = raw.match(/(?:expected calibration error|\bece\b)[^\d]{0,32}(0?\.\d+|\d+(?:\.\d+)?)/i)
    ece ??= eceMatch ? Number(eceMatch[1]) : null
    const count = raw.match(/(\d+)\s*(?:\/|of)\s*(\d+)/i)
    correct ??= count ? Number(count[1]) : null
    evaluated ??= count ? Number(count[2]) : null
    const evaluatedMatch = raw.match(/(?:evaluated transitions\s*\/\s*symbol outcomes|evaluated symbols)[^\d]{0,48}(\d+)/i)
    evaluated ??= evaluatedMatch ? Number(evaluatedMatch[1]) : null
  }
  if (accuracy === null && correct !== null && evaluated) accuracy = (correct / evaluated) * 100
  accuracy = percent(accuracy)
  directionalAccuracy = percent(directionalAccuracy)
  balancedAccuracy = percent(balancedAccuracy)
  macroF1 = percent(macroF1)
  coverage = percent(coverage)
  const hasEvaluation = evaluated !== null && evaluated > 0

  return {
    format: isJson ? 'JSON' : 'Markdown',
    status: hasEvaluation ? 'available' : 'pending',
    message: hasEvaluation ? null : 'No valid next-checkpoint outcomes are available for evaluation.',
    metrics: { accuracy, directionalAccuracy, balancedAccuracy, macroF1, mae, brier, ece, coverage, correct, evaluated },
  }
}

async function readVerification() {
  for (const path of verificationPaths) {
    try {
      const raw = await fs.readFile(path, 'utf8')
      return parseVerification(raw, path)
    } catch {
      // An optional report is allowed to be absent or not yet generated.
    }
  }
  return null
}

function isoAgeSeconds(value, now = Date.now()) {
  if (typeof value !== 'string') return null
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? Math.max(0, (now - timestamp) / 1000) : null
}

async function fileAgeSeconds(path, now = Date.now()) {
  try { return Math.max(0, (now - (await fs.stat(path)).mtimeMs) / 1000) } catch { return null }
}

function healthIssue(level, code, message) { return { level, code, message } }

async function loadHealth() {
  const generatedAt = new Date().toISOString()
  const now = Date.parse(generatedAt)
  const forecastMaxAgeSeconds = Number(process.env.FORECAST_MAX_AGE_SECONDS || 64800)
  const verificationMaxAgeSeconds = Number(process.env.VERIFICATION_MAX_AGE_SECONDS || 172800)
  const staleAfterSeconds = Number(process.env.QUOTE_MAX_AGE_SECONDS || 900)
  const warnings = []
  let forecast = null
  let forecastState = 'available'
  try { forecast = await readForecast() } catch (error) {
    forecastState = error instanceof SyntaxError ? 'invalid' : 'unavailable'
    warnings.push(healthIssue('error', error instanceof SyntaxError ? 'FORECAST_INVALID_JSON' : 'FORECAST_MISSING', 'Forecast snapshot is not available as valid JSON.'))
  }
  const asOf = stringValue(forecast?.as_of)
  const ageSeconds = isoAgeSeconds(asOf, now)
  let snapshotStatus = forecast ? 'available' : 'unavailable'
  if (forecast && ageSeconds === null) {
    snapshotStatus = 'invalid'
    warnings.push(healthIssue('error', 'FORECAST_TIMESTAMP_INVALID', 'Forecast as_of is missing or invalid.'))
  } else if (ageSeconds !== null && ageSeconds > forecastMaxAgeSeconds) {
    snapshotStatus = 'stale'
    warnings.push(healthIssue('warning', 'FORECAST_STALE', 'Forecast snapshot exceeds the configured maximum age.'))
  }
  const stocks = Array.isArray(forecast?.stocks) ? forecast.stocks : []
  const declaredUniverseCount = Number.isInteger(forecast?.universe_count) ? forecast.universe_count : null
  const universeCountConsistent = forecast ? declaredUniverseCount === stocks.length : false
  if (forecast && !universeCountConsistent) warnings.push(healthIssue('error', 'UNIVERSE_COUNT_MISMATCH', 'Declared universe_count does not match the stocks array.'))
  const quoteAges = stocks.map((stock) => finiteNumber(stock?.quote_freshness_seconds)).filter((value) => value !== null && value >= 0)
  const staleQuoteCount = quoteAges.filter((value) => value > staleAfterSeconds).length
  const missingQuoteAgeCount = stocks.length - quoteAges.length
  if (staleQuoteCount) warnings.push(healthIssue('warning', 'STALE_QUOTES', 'One or more saved quote observations are stale.'))
  if (missingQuoteAgeCount) warnings.push(healthIssue('warning', 'QUOTE_AGE_MISSING', 'One or more symbols lack quote freshness metadata.'))

  let verification = null
  let verificationSource = null
  let verificationTimestamp = null
  for (const path of verificationPaths) {
    try {
      const raw = await fs.readFile(path, 'utf8')
      verification = parseVerification(raw, path)
      if (extname(path).toLowerCase() === '.json') {
        const document = JSON.parse(raw)
        verificationTimestamp = stringValue(document?.generated_at) || stringValue(document?.generatedAt) || stringValue(document?.as_of)
      }
      verificationSource = path
      break
    } catch { /* optional */ }
  }
  let verificationAgeSeconds = isoAgeSeconds(verificationTimestamp, now)
  if (verificationAgeSeconds === null && verificationSource) verificationAgeSeconds = await fileAgeSeconds(verificationSource, now)
  if (!verification) warnings.push(healthIssue('warning', 'VERIFICATION_MISSING', 'Verification report is not available.'))
  else if (verification.status === 'pending') warnings.push(healthIssue('warning', 'VERIFICATION_PENDING', 'Verification has no evaluated outcomes.'))
  if (verificationAgeSeconds !== null && verificationAgeSeconds > verificationMaxAgeSeconds) warnings.push(healthIssue('warning', 'VERIFICATION_STALE', 'Verification report exceeds the configured maximum age.'))

  const upstreamSources = ['Google News RSS', 'Yahoo Finance chart'].map((name) => researchUpstreamState.get(name) || { name, status: 'unknown', checkedAt: null, error: null })
  return {
    ok: true, service: 'stock-analytics-dashboard',
    forecastSource: { status: forecastState, configured: true },
    latestSnapshot: { status: snapshotStatus, asOf, ageSeconds, maxAgeSeconds: forecastMaxAgeSeconds, slot: stringValue(forecast?.snapshot_slot) },
    verification: { status: verification?.status || 'unavailable', ageSeconds: verificationAgeSeconds, maxAgeSeconds: verificationMaxAgeSeconds, evaluated: verification?.metrics?.evaluated ?? null },
    dataQuality: { universeCount: stocks.length, declaredUniverseCount, universeCountConsistent, quoteAgeObservedCount: quoteAges.length, staleQuoteCount, missingQuoteAgeCount, staleAfterSeconds },
    researchUpstream: { status: upstreamSources.every((source) => source.status === 'available') ? 'available' : upstreamSources.some((source) => source.status === 'unavailable') ? 'degraded' : 'not_checked', sources: upstreamSources },
    warnings, generatedAt,
  }
}

async function loadDashboard() {
  const forecast = await readForecast()
  return { forecast, verification: await readVerification() }
}

function auditDataQuality(forecast) {
  const ages = (Array.isArray(forecast?.stocks) ? forecast.stocks : [])
    .map((stock) => finiteNumber(stock?.quote_freshness_seconds)).filter((value) => value !== null)
  const staleAfterSeconds = 900
  return {
    status: ages.length ? (ages.some((age) => age > staleAfterSeconds) ? 'stale' : 'available') : 'unavailable',
    observedSymbols: ages.length,
    minQuoteAgeSeconds: ages.length ? Math.min(...ages) : null,
    maxQuoteAgeSeconds: ages.length ? Math.max(...ages) : null,
    staleAfterSeconds,
    staleSymbolCount: ages.filter((age) => age > staleAfterSeconds).length,
    caveat: 'Freshness is copied from the saved forecast snapshot and may differ from independently refreshed live quotes.',
  }
}

function sanitizeForecastAudit(forecast, verification) {
  if (!forecast || typeof forecast !== 'object') {
    return { status: 'unavailable', message: 'Forecast audit metadata is unavailable.', forecast: null, verification: verification || null }
  }
  const stocks = (Array.isArray(forecast.stocks) ? forecast.stocks : []).map((stock) => {
    const probabilities = stock?.probabilities && typeof stock.probabilities === 'object'
      ? Object.fromEntries(['UP', 'FLAT', 'DOWN'].map((label) => [label, finiteNumber(stock.probabilities[label])]))
      : null
    return {
      symbol: stringValue(stock?.symbol), forecast: stringValue(stock?.forecast),
      confidence: stringValue(stock?.confidence), probabilities,
      modifier: stringValue(stock?.forecast_modifier), sentimentConflict: typeof stock?.sentiment_conflict === 'boolean' ? stock.sentiment_conflict : null,
      baselineTimestamp: stringValue(stock?.baseline_timestamp), quoteFreshnessSeconds: finiteNumber(stock?.quote_freshness_seconds),
    }
  }).filter((stock) => stock.symbol)
  return {
    status: 'available', message: null,
    forecast: {
      asOf: stringValue(forecast.as_of), horizon: stringValue(forecast.forecast_horizon), checkpoint: stringValue(forecast.snapshot_slot),
      modelVersion: stringValue(forecast.model_version), featureVersion: stringValue(forecast.feature_version), calibrationVersion: stringValue(forecast.calibration_version),
      universeCount: finiteNumber(forecast.universe_count), thresholdPct: finiteNumber(forecast.actual_threshold_pct), dataQuality: auditDataQuality(forecast), stocks,
    },
    verification: verification || { status: 'unavailable', message: 'Verification report is not mounted.', format: null, metrics: null },
  }
}

async function loadAudit() {
  let verification = await readVerification()
  try {
    return sanitizeForecastAudit(await readForecast(), verification)
  } catch {
    return { status: 'unavailable', message: 'Forecast audit source is not available or is invalid.', forecast: null, verification: verification || { status: 'unavailable', message: 'Verification report is not mounted.', format: null, metrics: null } }
  }
}

async function loadMethodology() {
  const audit = await loadAudit()
  return {
    status: 'available',
    versions: {
      model: { implementation: 'phase11-1.0', activeArtifact: audit.forecast?.modelVersion || null, status: audit.forecast?.modelVersion ? 'available' : 'unavailable' },
      features: { implementation: null, activeArtifact: audit.forecast?.featureVersion || null, status: audit.forecast?.featureVersion ? 'available' : 'unavailable' },
      calibration: { implementation: 'phase12-1.0', activeArtifact: audit.forecast?.calibrationVersion || null, status: audit.forecast?.calibrationVersion ? 'available' : 'unavailable' },
      archiveSchema: '1.0',
    },
    checkpointHorizons: ['close 16:01 WIB → next trading-day open 09:01 WIB', 'open 09:01 WIB → break 12:01 WIB', 'break 12:01 WIB → close 16:01 WIB'],
    metricDefinitions: {
      accuracy: 'Share of evaluated outcomes whose three-way UP/FLAT/DOWN class matches.',
      balancedAccuracy: 'Mean recall across outcome classes that have support.', macroF1: 'Mean class F1 across classes that have support.',
      mae: 'Mean absolute error between target and realized return, in percentage points.', brier: 'Mean squared error of the full three-way probability vector; lower is better.',
      ece: 'Expected calibration error between confidence and observed accuracy; lower is better.', coverage: 'Evaluated valid outcomes divided by eligible forecasts.',
    },
    dataSeparationPolicy: 'Chronological only: base models fit on training rows, calibration fits on validation rows, and test rows are reserved exclusively for evaluation; horizon-aware purging and embargoes prevent lookahead.',
    staleDataCaveat: 'Saved forecast inputs can be delayed or stale. Snapshot freshness does not imply current market freshness, and live quote refreshes are independent.',
    disclaimer: 'Read-only analytical context. Not for trade execution and not investment advice.',
    forecastHealth: audit.forecast ? audit.forecast.dataQuality : { status: 'unavailable' },
    evaluationCoverage: audit.verification?.metrics ? { status: audit.verification.status, evaluated: audit.verification.metrics.evaluated, coveragePct: audit.verification.metrics.coverage } : { status: 'unavailable', evaluated: null, coveragePct: null },
  }
}

function normalizeQuoteSymbol(raw) {
  const value = raw.trim().toUpperCase()
  if (!quoteSymbolPattern.test(value)) return null
  return value.endsWith('.JK') ? value.slice(0, -3) : value
}

async function fetchQuote(symbol) {
  const yahooSymbol = `${symbol}.JK`
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 7000)
  try {
    const endpoint = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol)}?range=5d&interval=1d&includePrePost=false`
    const response = await fetch(endpoint, {
      headers: { 'User-Agent': 'stock-analytics-dashboard/1.0' },
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Yahoo returned ${response.status}`)
    const body = await response.json()
    const chart = body?.chart?.result?.[0]
    if (!chart) throw new Error('No chart data')
    const meta = chart.meta || {}
    const closes = (chart.indicators?.quote?.[0]?.close || []).filter((value) => Number.isFinite(value))
    const price = Number(meta.regularMarketPrice ?? closes.at(-1))
    const previousClose = Number(meta.previousClose ?? closes.at(-2))
    if (!Number.isFinite(price)) throw new Error('No latest price')
    const change = Number.isFinite(previousClose) ? price - previousClose : null
    return {
      symbol,
      yahooSymbol,
      price,
      previousClose: Number.isFinite(previousClose) ? previousClose : null,
      change,
      changePct: change !== null && previousClose ? (change / previousClose) * 100 : null,
      asOf: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
    }
  } catch (error) {
    return { symbol, yahooSymbol, error: error instanceof Error ? error.message : 'Quote unavailable' }
  } finally {
    clearTimeout(timeout)
  }
}

function normalizeChartRequest(url) {
  const rawSymbol = url.searchParams.get('symbol')
  const range = url.searchParams.get('range')
  const interval = url.searchParams.get('interval')
  const symbol = rawSymbol ? normalizeQuoteSymbol(rawSymbol) : null
  if (!symbol) return { error: 'symbol must be an IDX ticker such as BBCA or BBCA.JK.' }
  if (!range || !chartRanges.has(range)) return { error: 'range must be one of 1d, 5d, 1mo, 3mo, or 1y.' }
  if (!interval || !chartIntervals.has(interval)) return { error: 'interval must be one of 5m, 15m, 1h, or 1d.' }
  return { symbol, range, interval }
}

function normalizeChartBars(chart) {
  const timestamps = Array.isArray(chart?.timestamp) ? chart.timestamp : []
  const quote = chart?.indicators?.quote?.[0] || {}
  const bars = timestamps.map((timestamp, index) => {
    const time = Number(timestamp)
    const open = Number(quote.open?.[index])
    const high = Number(quote.high?.[index])
    const low = Number(quote.low?.[index])
    const close = Number(quote.close?.[index])
    const volume = Number(quote.volume?.[index])
    if (![time, open, high, low, close].every(Number.isFinite) || time <= 0 || open <= 0 || high <= 0 || low <= 0 || close <= 0) return null
    const normalizedHigh = Math.max(open, high, low, close)
    const normalizedLow = Math.min(open, high, low, close)
    return {
      time: Math.trunc(time),
      open,
      high: normalizedHigh,
      low: normalizedLow,
      close,
      volume: Number.isFinite(volume) ? Math.max(0, volume) : 0,
    }
  }).filter(Boolean)
  return [...new Map(bars.map((bar) => [bar.time, bar])).values()].sort((left, right) => left.time - right.time)
}

async function fetchChart(symbol, range, interval) {
  const cacheKey = `${symbol}:${range}:${interval}`
  const cached = chartCache.get(cacheKey)
  if (cached && Date.now() - cached.at < 30000) return cached.payload

  const yahooSymbol = `${symbol}.JK`
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const endpoint = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol)}?range=${encodeURIComponent(range)}&interval=${encodeURIComponent(interval)}&includePrePost=false&events=div%2Csplits`
    const response = await fetch(endpoint, {
      headers: { 'User-Agent': 'stock-analytics-dashboard/1.0' },
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Yahoo returned ${response.status}`)
    const body = await response.json()
    if (body?.chart?.error) throw new Error('Yahoo returned chart data error')
    const chart = body?.chart?.result?.[0]
    const bars = normalizeChartBars(chart)
    if (!bars.length) throw new Error('No chart data available')
    const payload = {
      symbol,
      yahooSymbol,
      range,
      interval,
      bars,
      meta: {
        currency: chart?.meta?.currency || 'IDR',
        exchangeTimezoneName: chart?.meta?.exchangeTimezoneName || 'Asia/Jakarta',
        dataGranularity: chart?.meta?.dataGranularity || interval,
      },
      source: 'Yahoo Finance chart API',
      fetchedAt: new Date().toISOString(),
    }
    chartCache.set(cacheKey, { at: Date.now(), payload })
    return payload
  } finally {
    clearTimeout(timeout)
  }
}

async function limitedMap(items, limit, worker) {
  const results = []
  let cursor = 0
  async function consume() {
    while (cursor < items.length) {
      const item = items[cursor++]
      results.push(await worker(item))
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, consume))
  return results
}

async function loadQuotes(symbols) {
  const uniqueSymbols = [...new Set(symbols)]
  const now = Date.now()
  const staleSymbols = uniqueSymbols.filter((symbol) => {
    const cached = quoteCache.get(symbol)
    return !cached || now - cached.at >= 20000
  })
  if (staleSymbols.length) {
    const freshQuotes = await limitedMap(staleSymbols, 8, fetchQuote)
    const fetchedAt = Date.now()
    freshQuotes.forEach((quote) => quoteCache.set(quote.symbol, { at: fetchedAt, quote }))
  }
  return uniqueSymbols.map((symbol) => quoteCache.get(symbol)?.quote).filter(Boolean)
}

function decodeXml(value = '') {
  return value.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'")
}

function xmlText(block, tag) {
  const match = block.match(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, 'i'))
  return match ? decodeXml(match[1]).replace(/<[^>]+>/g, '').trim() : ''
}

function upstreamError(error) {
  if (error?.name === 'AbortError') return { code: 'UPSTREAM_TIMEOUT', message: 'Request timed out.', retriable: true }
  if (error instanceof SyntaxError) return { code: 'UPSTREAM_INVALID_RESPONSE', message: 'Response could not be parsed.', retriable: false }
  const match = error instanceof Error ? error.message.match(/^HTTP (\d+)$/) : null
  if (match) {
    const status = Number(match[1])
    return { code: 'UPSTREAM_HTTP_ERROR', message: `Upstream returned HTTP ${status}.`, httpStatus: status, retriable: status === 429 || status >= 500 }
  }
  return { code: 'UPSTREAM_REQUEST_FAILED', message: 'Upstream request failed.', retriable: true }
}

async function fetchWithRetry(endpoint, source) {
  let failure
  for (let attempt = 1; attempt <= researchMaxAttempts; attempt += 1) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), researchTimeoutMs)
    try {
      const response = await fetch(endpoint, { headers: { 'User-Agent': 'stock-analytics-dashboard/1.0' }, signal: controller.signal })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      researchUpstreamState.set(source, { name: source, status: 'available', checkedAt: new Date().toISOString(), error: null })
      return { response, attempts: attempt }
    } catch (error) {
      failure = upstreamError(error)
      if (!failure.retriable || attempt === researchMaxAttempts) break
    } finally { clearTimeout(timeout) }
  }
  researchUpstreamState.set(source, { name: source, status: 'unavailable', checkedAt: new Date().toISOString(), error: failure })
  const error = new Error(failure.message)
  error.metadata = failure
  error.attempts = failure.retriable ? researchMaxAttempts : 1
  throw error
}

async function fetchRss(label, query) {
  try {
    const endpoint = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-ID&gl=ID&ceid=ID:en`
    const { response, attempts } = await fetchWithRetry(endpoint, 'Google News RSS')
    const xml = await response.text()
    const items = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/gi)].slice(0, 8).map((match) => {
      const block = match[1]
      const publishedAt = xmlText(block, 'pubDate')
      return { title: xmlText(block, 'title'), url: xmlText(block, 'link'), source: xmlText(block, 'source') || 'Google News', publishedAt: publishedAt && !Number.isNaN(Date.parse(publishedAt)) ? new Date(publishedAt).toISOString() : null }
    }).filter((item) => item.title && /^https:\/\//.test(item.url))
    return { label, status: 'available', source: 'Google News RSS', fetchedAt: new Date().toISOString(), items, request: { timeoutMs: researchTimeoutMs, attempts, retryCount: attempts - 1 } }
  } catch (error) {
    const metadata = error?.metadata || upstreamError(error)
    researchUpstreamState.set('Google News RSS', { name: 'Google News RSS', status: 'unavailable', checkedAt: new Date().toISOString(), error: metadata })
    const attempts = error?.attempts || 1
    return { label, status: 'unavailable', source: 'Google News RSS', fetchedAt: new Date().toISOString(), items: [], message: 'Upstream news is unavailable.', request: { timeoutMs: researchTimeoutMs, attempts, retryCount: attempts - 1, error: metadata } }
  }
}

const positiveTerms = /\b(gain|growth|rise|rally|record|profit|upgrade|surge|strong|optimis|naik|untung)\b/i
const negativeTerms = /\b(loss|fall|drop|risk|cut|weak|decline|slump|probe|lawsuit|turun|rugi)\b/i

function sentimentLayer(name, items, unavailableMessage, fetchedAt) {
  if (!items.length) return { name, tone: 'unavailable', regime: 'insufficient data', impact: unavailableMessage, confidence: 'low', observations: 0, source: 'Google News RSS', fetchedAt }
  let score = 0
  for (const item of items) score += positiveTerms.test(item.title) ? 1 : negativeTerms.test(item.title) ? -1 : 0
  const tone = score > 0 ? 'positive' : score < 0 ? 'negative' : 'neutral'
  const regime = Math.abs(score) >= 3 ? 'directional' : 'mixed'
  const confidence = items.length >= 6 && Math.abs(score) >= 2 ? 'medium' : 'low'
  return { name, tone, regime, impact: `Headline tone is ${tone}; treat as context pending fundamental verification.`, confidence, observations: items.length, source: 'Google News RSS', fetchedAt }
}

async function fetchMarketContext(symbol, yahooSymbol, name) {
  try {
    const { response, attempts } = await fetchWithRetry(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol)}?range=5d&interval=1d`, 'Yahoo Finance chart')
    const body = await response.json()
    const bars = normalizeChartBars(body?.chart?.result?.[0])
    const first = bars[0]?.close
    const last = bars.at(-1)?.close
    const changePct = first && last ? ((last - first) / first) * 100 : null
    const tone = changePct === null ? 'neutral' : changePct > 0.5 ? 'positive' : changePct < -0.5 ? 'negative' : 'neutral'
    return { name, tone, regime: changePct === null ? 'insufficient data' : `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}% / 5d`, impact: `${symbol} may be influenced by this market backdrop.`, confidence: changePct === null ? 'low' : 'medium', observations: bars.length, source: `Yahoo Finance chart (${yahooSymbol})`, fetchedAt: new Date().toISOString(), request: { timeoutMs: researchTimeoutMs, attempts, retryCount: attempts - 1 } }
  } catch (error) {
    const metadata = error?.metadata || upstreamError(error)
    researchUpstreamState.set('Yahoo Finance chart', { name: 'Yahoo Finance chart', status: 'unavailable', checkedAt: new Date().toISOString(), error: metadata })
    const attempts = error?.attempts || 1
    return { name, tone: 'unavailable', regime: 'insufficient data', impact: 'Yahoo market context is temporarily unavailable.', confidence: 'low', observations: 0, source: `Yahoo Finance chart (${yahooSymbol})`, fetchedAt: new Date().toISOString(), request: { timeoutMs: researchTimeoutMs, attempts, retryCount: attempts - 1, error: metadata } }
  }
}

async function loadResearch(symbol) {
  const cached = researchCache.get(symbol)
  if (cached && Date.now() - cached.at < researchCacheMs) return cached.payload
  const fetchedAt = new Date().toISOString()
  const [company, indonesia, global, indonesiaMarket, globalMarket] = await Promise.all([
    fetchRss('company', `"${symbol}" IDX OR "${symbol}.JK" when:14d`),
    fetchRss('indonesia', 'Indonesia stock market IHSG economy when:7d'),
    fetchRss('global', 'global markets central banks commodities Asia when:7d'),
    fetchMarketContext(symbol, '^JKSE', 'Indonesia market'),
    fetchMarketContext(symbol, '^GSPC', 'Global'),
  ])
  const sectorItems = company.items
  const sources = [company, indonesia, global].map(({ label, status, source, fetchedAt: sourceFetchedAt, message, items, request }) => ({ label, status, source, fetchedAt: sourceFetchedAt, itemCount: items.length, request, ...(message ? { message } : {}) }))
  const payload = {
    symbol, yahooSymbol: `${symbol}.JK`, fetchedAt, cacheTtlSeconds: researchCacheMs / 1000,
    freshness: 'Runtime fetch; news queries cover the last 7–14 days.',
    news: company.items.slice(0, 6), sources,
    layers: [
      globalMarket.observations ? globalMarket : sentimentLayer('Global', global.items, 'Global context sources are temporarily unavailable.', global.fetchedAt),
      indonesiaMarket.observations ? indonesiaMarket : sentimentLayer('Indonesia market', indonesia.items, 'Indonesia market sources are temporarily unavailable.', indonesia.fetchedAt),
      sentimentLayer('Sector', sectorItems, 'No reliable sector-specific items were discovered for this ticker.', company.fetchedAt),
      sentimentLayer('Company', company.items, 'No current company headlines were discovered; no sentiment was inferred.', company.fetchedAt),
    ],
    unavailable: company.items.length ? null : 'No current company headlines are available from the public source. No placeholder headlines were generated.',
    disclaimer: 'Sentiment is analytical context, not investment advice.',
  }
  researchCache.set(symbol, { at: Date.now(), payload })
  return payload
}

async function serveStatic(res, pathname) {
  let decoded
  try {
    decoded = decodeURIComponent(pathname)
  } catch {
    res.writeHead(400)
    res.end('Bad request')
    return
  }
  const requested = decoded === '/' ? '/index.html' : decoded
  let filePath = resolve(distDir, `.${requested}`)
  if (filePath !== distDir && !filePath.startsWith(`${distDir}${sep}`)) {
    res.writeHead(403)
    res.end('Forbidden')
    return
  }
  try {
    const file = await fs.readFile(filePath)
    res.writeHead(200, {
      'Content-Type': mimeTypes[extname(filePath)] || 'application/octet-stream',
      'Cache-Control': extname(filePath) === '.html' ? 'no-cache' : 'public, max-age=31536000, immutable',
    })
    res.end(file)
  } catch {
    if (!extname(requested)) {
      filePath = join(distDir, 'index.html')
      try {
        const file = await fs.readFile(filePath)
        res.writeHead(200, { 'Content-Type': mimeTypes['.html'], 'Cache-Control': 'no-cache' })
        res.end(file)
        return
      } catch {
        // Fall through to the useful build hint below.
      }
    }
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
    res.end('Dashboard build not found. Run npm run build first.')
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`)
  if (req.method !== 'GET') {
    sendJson(res, 405, { error: 'Read-only API: GET requests only.' })
    return
  }
  try {
    if (url.pathname === '/api/health') {
      sendJson(res, 200, await loadHealth())
      return
    }
    if (url.pathname === '/api/audit') {
      sendJson(res, 200, await loadAudit())
      return
    }
    if (url.pathname === '/api/methodology') {
      sendJson(res, 200, await loadMethodology())
      return
    }
    if (url.pathname === '/api/dashboard') {
      sendJson(res, 200, await loadDashboard())
      return
    }
    if (url.pathname === '/api/quotes') {
      const dashboard = await loadDashboard()
      const rawSymbols = url.searchParams.get('symbols')
      let symbols
      if (rawSymbols === null) {
        symbols = dashboard.forecast.stocks.map((stock) => stock.symbol)
      } else {
        const rawValues = rawSymbols.split(',')
        if (rawValues.length > maxQuoteSymbols) {
          sendJson(res, 400, { error: `A maximum of ${maxQuoteSymbols} symbols can be requested.` })
          return
        }
        const invalidValues = rawValues.filter((value) => !normalizeQuoteSymbol(value))
        if (invalidValues.length) {
          sendJson(res, 400, { error: 'symbols must be comma-separated IDX tickers such as BBCA or BBCA.JK.' })
          return
        }
        symbols = [...new Set(rawValues.map(normalizeQuoteSymbol))]
      }
      const quotes = await loadQuotes(symbols)
      sendJson(res, 200, { quotes, fetchedAt: new Date().toISOString(), source: 'Yahoo Finance chart API' })
      return
    }
    if (url.pathname === '/api/chart') {
      const request = normalizeChartRequest(url)
      if (request.error) {
        sendJson(res, 400, { error: request.error })
        return
      }
      try {
        const payload = await fetchChart(request.symbol, request.range, request.interval)
        sendJson(res, 200, payload)
      } catch (error) {
        console.warn(`Chart request failed for ${request.symbol}`, error instanceof Error ? error.message : error)
        sendJson(res, 502, { error: 'Chart data is temporarily unavailable from Yahoo Finance.' })
      }
      return
    }
    if (url.pathname === '/api/research') {
      const rawSymbol = url.searchParams.get('symbol')
      const symbol = rawSymbol ? normalizeQuoteSymbol(rawSymbol) : null
      if (!symbol) {
        sendJson(res, 400, { error: 'symbol must be an IDX ticker such as BBCA or BBCA.JK.' })
        return
      }
      sendJson(res, 200, await loadResearch(symbol))
      return
    }
    await serveStatic(res, url.pathname)
  } catch (error) {
    sendJson(res, 500, { error: error instanceof Error ? error.message : 'Server error' })
  }
})

server.listen(port, host, () => {
  console.log(`Stock analytics dashboard listening on http://${host}:${port}`)
  console.log(`Forecast source: ${forecastPath}`)
})
