import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

async function waitFor(url) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try { const response = await fetch(url); if (response.ok) return } catch { /* starting */ }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  throw new Error('test server did not start')
}

test('Phase 13 audit is sanitized and methodology is explicit', async (context) => {
  const directory = await mkdtemp(join(tmpdir(), 'stock-dashboard-phase13-'))
  const forecastFile = join(directory, 'forecast.json')
  const verificationFile = join(directory, 'verification.json')
  await writeFile(forecastFile, JSON.stringify({ as_of: '2026-08-12T16:06:26+07:00', source: 'secret source', snapshot_slot: 'close_1601_wib', forecast_horizon: 'next_open', actual_threshold_pct: 0.25, universe_count: 1, sources: [{ url: 'https://secret.example/research' }], stocks: [{ symbol: 'BBCA', forecast: 'UP', confidence: 'medium', forecast_modifier: 'mixed', sentiment_conflict: true, quote_freshness_seconds: 901, baseline_timestamp: '2026-08-12T15:49:58+07:00', sentiment_context: { company: { source: 'https://secret.example/article' } } }] }))
  await writeFile(verificationFile, JSON.stringify({ metrics: { accuracy_pct: 60, balanced_accuracy_pct: 55, macro_f1_pct: 50, target_mae_pct: 0.4, brier_score: 0.3, expected_calibration_error: 0.08, coverage_pct: 80, evaluated: 8 } }))
  const port = 43000 + (process.pid % 1000)
  const child = spawn(process.execPath, ['server.mjs'], { cwd: process.cwd(), env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), FORECAST_FILE: forecastFile, VERIFICATION_FILE: verificationFile }, stdio: 'ignore' })
  context.after(() => child.kill())
  const base = `http://127.0.0.1:${port}`
  await waitFor(`${base}/api/health`)
  const auditResponse = await fetch(`${base}/api/audit`)
  const auditText = await auditResponse.text()
  const audit = JSON.parse(auditText)
  assert.equal(audit.status, 'available')
  assert.equal(audit.forecast.stocks[0].modifier, 'mixed')
  assert.equal(audit.forecast.dataQuality.status, 'stale')
  assert.equal(audit.verification.metrics.balancedAccuracy, 55)
  assert.equal(audit.verification.metrics.brier, 0.3)
  assert.doesNotMatch(auditText, /secret\.example|sentiment_context|forecast\.json|verification\.json/)
  const methodology = await (await fetch(`${base}/api/methodology`)).json()
  assert.equal(methodology.versions.model.activeArtifact, null)
  assert.equal(methodology.versions.model.status, 'unavailable')
  assert.equal(methodology.evaluationCoverage.evaluated, 8)
  assert.match(methodology.disclaimer, /Not for trade execution/)
  assert.equal((await fetch(`${base}/api/audit`, { method: 'POST' })).status, 405)
})
