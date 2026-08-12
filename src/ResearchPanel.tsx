import { useEffect, useState } from 'react'

type Language = 'EN' | 'ID' | 'MY' | 'CN'
type Research = {
  symbol: string
  fetchedAt: string
  freshness: string
  news: { title: string; url: string; source: string; publishedAt: string | null }[]
  sources: { label: string; status: string; source: string; fetchedAt: string; itemCount: number; message?: string }[]
  layers: { name: string; tone: string; regime: string; impact: string; confidence: string; observations: number; source: string; fetchedAt: string }[]
  unavailable: string | null
}

const labels: Record<Language, Record<string, string>> = {
  EN: { title: 'RESEARCH TERMINAL', news: 'Company news', context: 'Sentiment / context layers', loading: 'Fetching public-source research…', retry: 'Retry', empty: 'No current company headlines were returned.', warning: 'Sentiment is analytical context, not investment advice.', source: 'Source', fetched: 'Fetched', impact: 'Impact', confidence: 'Confidence', observations: 'observations' },
  ID: { title: 'TERMINAL RISET', news: 'Berita perusahaan', context: 'Lapisan sentimen / konteks', loading: 'Mengambil riset dari sumber publik…', retry: 'Coba lagi', empty: 'Tidak ada berita perusahaan terkini dari sumber publik.', warning: 'Sentimen adalah konteks analitis, bukan nasihat investasi.', source: 'Sumber', fetched: 'Diambil', impact: 'Dampak', confidence: 'Keyakinan', observations: 'observasi' },
  MY: { title: 'TERMINAL KAJIAN', news: 'Berita syarikat', context: 'Lapisan sentimen / konteks', loading: 'Mengambil kajian sumber awam…', retry: 'Cuba lagi', empty: 'Tiada berita syarikat semasa daripada sumber awam.', warning: 'Sentimen ialah konteks analisis, bukan nasihat pelaburan.', source: 'Sumber', fetched: 'Diambil', impact: 'Impak', confidence: 'Keyakinan', observations: 'pemerhatian' },
  CN: { title: '研究终端', news: '公司新闻', context: '情绪 / 背景层', loading: '正在获取公共来源研究…', retry: '重试', empty: '公共来源未返回近期公司新闻。', warning: '情绪仅供分析参考，不构成投资建议。', source: '来源', fetched: '获取时间', impact: '影响', confidence: '信心', observations: '条观察' },
}

function stamp(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? '—' : date.toLocaleString()
}

export function ResearchPanel({ symbol, language }: { symbol: string; language: Language }) {
  const [data, setData] = useState<Research | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const t = labels[language]

  useEffect(() => {
    const controller = new AbortController()
    setData(null); setError('')
    fetch(`/api/research?symbol=${encodeURIComponent(symbol)}`, { signal: controller.signal })
      .then(async (response) => { const body = await response.json(); if (!response.ok) throw new Error(body.error || 'Research unavailable'); return body })
      .then(setData).catch((reason) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [symbol, attempt])

  return <section className="research-panel" aria-live="polite">
    <header className="research-header"><div><div className="section-kicker amber-text">{t.title}</div><h3>{symbol}<span>.JK</span></h3></div>{data && <div className="research-freshness">{t.fetched} · {stamp(data.fetchedAt)}<br />{data.freshness}</div>}</header>
    {!data && !error && <div className="research-state"><span className="spinner" />{t.loading}</div>}
    {error && <div className="research-state negative">{error} <button className="button" onClick={() => setAttempt((value) => value + 1)}>{t.retry}</button></div>}
    {data && <>
      <div className="research-layers"><div className="research-subtitle">{t.context}</div>{data.layers.map((layer) => <article className="research-layer" key={layer.name}>
        <div className="layer-top"><strong>{layer.name}</strong><span className={`tone ${layer.tone}`}>{layer.tone} / {layer.regime}</span></div>
        <p><b>{t.impact}</b> · {layer.impact}</p><small>{t.confidence}: {layer.confidence} · {layer.observations} {t.observations}<br />{t.source}: {layer.source}<br />{t.fetched}: {stamp(layer.fetchedAt)}</small>
      </article>)}</div>
      <div className="research-news"><div className="research-subtitle">{t.news}</div>{data.news.length ? <ul>{data.news.map((item) => <li key={`${item.url}-${item.title}`}><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a><span>{item.source} · {stamp(item.publishedAt)}</span></li>)}</ul> : <div className="research-empty">{data.unavailable || t.empty}</div>}
        <div className="source-strip">{data.sources.map((source) => <span key={source.label} title={source.message}>{t.source}: {source.source} / {source.label} · {source.status} · {source.itemCount}</span>)}</div>
      </div>
      <p className="research-warning">⚠ {t.warning}</p>
    </>}
  </section>
}
