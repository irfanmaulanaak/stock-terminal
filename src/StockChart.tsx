import { useEffect, useRef, useState } from 'react'
import { CandlestickSeries, HistogramSeries, createChart, type IChartApi, type UTCTimestamp } from 'lightweight-charts'

type Language = 'EN' | 'ID' | 'MY' | 'CN'
export type ChartRange = '1d' | '5d' | '1mo' | '3mo' | '1y'

interface ForecastInput {
  baseline: number
  target_return_pct: number
  forecast: 'UP' | 'FLAT' | 'DOWN'
}

interface QuoteInput {
  price?: number
}

interface ChartBar {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface ChartPayload {
  bars: ChartBar[]
  source: string
  fetchedAt: string
  interval: string
  meta?: { currency?: string; exchangeTimezoneName?: string }
}

const rangeOptions: Array<{ range: ChartRange; interval: string }> = [
  { range: '1d', interval: '5m' },
  { range: '5d', interval: '15m' },
  { range: '1mo', interval: '1h' },
  { range: '3mo', interval: '1d' },
  { range: '1y', interval: '1d' },
]

const labels: Record<Language, Record<string, string>> = {
  EN: {
    chart: 'PRICE CHART', expand: 'Open chart', collapse: 'Close chart', loading: 'Loading chart…', error: 'Chart data unavailable.', noData: 'No chart data for this range.', range: 'Range', baseline: 'Baseline', current: 'Current', target: 'Target', volume: 'Volume', updated: 'Fetched', disclaimer: 'Yahoo Finance data may be delayed. For research only; not a trading instruction.', attribution: 'Charts by TradingView Lightweight Charts', retry: 'Retry',
  },
  ID: {
    chart: 'GRAFIK HARGA', expand: 'Buka grafik', collapse: 'Tutup grafik', loading: 'Memuat grafik…', error: 'Data grafik tidak tersedia.', noData: 'Tidak ada data grafik untuk rentang ini.', range: 'Rentang', baseline: 'Baseline', current: 'Kini', target: 'Target', volume: 'Volume', updated: 'Diambil', disclaimer: 'Data Yahoo Finance dapat tertunda. Untuk riset saja; bukan instruksi trading.', attribution: 'Grafik oleh TradingView Lightweight Charts', retry: 'Coba lagi',
  },
  MY: {
    chart: 'GRAF HARGA', expand: 'Buka graf', collapse: 'Tutup graf', loading: 'Memuatkan graf…', error: 'Data graf tidak tersedia.', noData: 'Tiada data graf untuk julat ini.', range: 'Julat', baseline: 'Baseline', current: 'Kini', target: 'Sasaran', volume: 'Volum', updated: 'Diambil', disclaimer: 'Data Yahoo Finance mungkin tertangguh. Untuk kajian sahaja; bukan arahan dagangan.', attribution: 'Graf oleh TradingView Lightweight Charts', retry: 'Cuba lagi',
  },
  CN: {
    chart: '价格图表', expand: '打开图表', collapse: '关闭图表', loading: '正在加载图表…', error: '图表数据不可用。', noData: '此范围没有图表数据。', range: '范围', baseline: '基准价', current: '当前', target: '目标', volume: '成交量', updated: '获取时间', disclaimer: 'Yahoo Finance 数据可能有延迟。仅供研究，不是交易指令。', attribution: '图表由 TradingView Lightweight Charts 提供', retry: '重试',
  },
}

function text(language: Language, key: string) {
  return labels[language][key] || labels.EN[key] || key
}

function formatPrice(value: number | null) {
  return value === null || !Number.isFinite(value) ? '—' : `Rp ${new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)}`
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}

function ChartCanvas({ payload, forecast, quote, baseline, current, target }: { payload: ChartPayload; forecast: ForecastInput; quote?: QuoteInput; baseline: number; current: number | null; target: number }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container || !payload.bars.length) return
    const chart: IChartApi = createChart(container, {
      width: container.clientWidth,
      height: 330,
      layout: { background: { color: 'transparent' }, textColor: '#9c9185', fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, monospace', fontSize: 10 },
      grid: { vertLines: { color: '#302a25' }, horzLines: { color: '#302a25' } },
      crosshair: { mode: 0, vertLine: { color: '#e2a64b', width: 1, style: 2 }, horzLine: { color: '#e2a64b', width: 1, style: 2 } },
      rightPriceScale: { borderColor: '#40382f', scaleMargins: { top: 0.08, bottom: 0.25 } },
      timeScale: { borderColor: '#40382f', timeVisible: true, secondsVisible: false },
    })
    const candles = chart.addSeries(CandlestickSeries, { upColor: '#72c78a', downColor: '#df7570', borderVisible: false, wickUpColor: '#72c78a', wickDownColor: '#df7570' })
    candles.setData(payload.bars.map((bar) => ({ time: bar.time as UTCTimestamp, open: bar.open, high: bar.high, low: bar.low, close: bar.close })))
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'volume', color: '#756b61' })
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } })
    volume.setData(payload.bars.map((bar) => ({ time: bar.time as UTCTimestamp, value: bar.volume, color: bar.close >= bar.open ? '#72c78a55' : '#df757055' })))
    const addLine = (price: number, color: string, title: string, lineStyle: 1 | 2 = 2) => {
      if (Number.isFinite(price)) candles.createPriceLine({ price, color, lineWidth: 1, lineStyle, axisLabelVisible: true, title })
    }
    addLine(baseline, '#e2a64b', 'B')
    if (current !== null) addLine(current, '#eee8df', 'C', 1)
    addLine(target, forecast.forecast === 'DOWN' ? '#df7570' : '#72c78a', 'T')
    chart.timeScale().fitContent()
    const resize = () => chart.applyOptions({ width: container.clientWidth })
    const observer = new ResizeObserver(resize)
    observer.observe(container)
    window.addEventListener('resize', resize)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', resize)
      chart.remove()
    }
  }, [baseline, current, forecast.forecast, payload, target])

  return <div className="stock-chart-canvas" ref={containerRef} aria-label="Interactive candlestick and volume chart" />
}

export function StockChart({ language, symbol, forecast, quote }: { language: Language; symbol: string; forecast: ForecastInput; quote?: QuoteInput }) {
  const [range, setRange] = useState<ChartRange>('3mo')
  const [payload, setPayload] = useState<ChartPayload | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [retryToken, setRetryToken] = useState(0)
  const selectedRange = rangeOptions.find((option) => option.range === range) || rangeOptions[3]
  const current = quote?.price !== undefined && Number.isFinite(quote.price) ? quote.price : null
  const target = forecast.baseline * (1 + forecast.target_return_pct / 100)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    fetch(`/api/chart?symbol=${encodeURIComponent(symbol)}&range=${selectedRange.range}&interval=${selectedRange.interval}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json() as ChartPayload & { error?: string }
        if (!response.ok) throw new Error(body.error || text(language, 'error'))
        return body
      })
      .then((body) => setPayload(body))
      .catch((caught) => {
        if (!controller.signal.aborted) {
          setPayload(null)
          setError(caught instanceof Error ? caught.message : text(language, 'error'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [language, retryToken, selectedRange.interval, selectedRange.range, symbol])

  return (
    <div className="stock-chart" aria-label={`${symbol} ${text(language, 'chart')}`}>
      <div className="stock-chart-header">
        <div><div className="section-kicker amber-text">{text(language, 'chart')} / {symbol}.JK</div><div className="chart-legend"><span className="chart-legend-item baseline"><i />{text(language, 'baseline')} {formatPrice(forecast.baseline)}</span><span className="chart-legend-item current"><i />{text(language, 'current')} {formatPrice(current)}</span><span className={`chart-legend-item ${forecast.forecast === 'DOWN' ? 'target-down' : 'target-up'}`}><i />{text(language, 'target')} {formatPrice(target)}</span></div></div>
        <div className="chart-range" aria-label={text(language, 'range')}><span>{text(language, 'range')}</span>{rangeOptions.map((option) => <button className={range === option.range ? 'selected' : ''} key={option.range} onClick={() => setRange(option.range)} type="button">{option.range}</button>)}</div>
      </div>
      {loading && <div className="chart-message"><span className="spinner small" />{text(language, 'loading')}</div>}
      {!loading && error && <div className="chart-message chart-error">{error}<button className="button" onClick={() => setRetryToken((value) => value + 1)} type="button">{text(language, 'retry')}</button></div>}
      {!loading && !error && payload && <ChartCanvas payload={payload} forecast={forecast} quote={quote} baseline={forecast.baseline} current={current} target={target} />}
      {!loading && !error && !payload && <div className="chart-message">{text(language, 'noData')}</div>}
      {payload && !loading && !error && <div className="stock-chart-footer"><span>{payload.source} · {text(language, 'updated')} {formatDate(payload.fetchedAt)} UTC</span><span>{text(language, 'volume')} · {payload.interval}</span><a href="https://tradingview.github.io/lightweight-charts/" target="_blank" rel="noreferrer">{text(language, 'attribution')} ↗</a></div>}
      <p className="chart-disclaimer">{text(language, 'disclaimer')}</p>
    </div>
  )
}
