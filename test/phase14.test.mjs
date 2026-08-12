import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, writeFile } from 'node:fs/promises'
import net from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

async function freePort() {
  return new Promise((resolve, reject) => { const server = net.createServer(); server.on('error', reject); server.listen(0, '127.0.0.1', () => { const port = server.address().port; server.close(() => resolve(port)) }) })
}
async function waitFor(url) {
  for (let attempt = 0; attempt < 60; attempt += 1) { try { const response = await fetch(url); if (response.ok) return } catch {} await new Promise((resolve) => setTimeout(resolve, 50)) }
  throw new Error('test server did not start')
}
async function withServer(context, environment) {
  const port = await freePort()
  const child = spawn(process.execPath, ['server.mjs'], { cwd: process.cwd(), env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), ...environment }, stdio: 'ignore' })
  context.after(() => child.kill())
  const base = `http://127.0.0.1:${port}`
  await waitFor(`${base}/api/health`)
  return base
}

test('Phase 14 health reports a healthy mounted state without exposing paths', async (context) => {
  const directory = await mkdtemp(join(tmpdir(), 'stock-dashboard-phase14-'))
  const forecastFile = join(directory, 'forecast.json'); const verificationFile = join(directory, 'verification.json')
  await writeFile(forecastFile, JSON.stringify({ as_of: new Date().toISOString(), snapshot_slot: 'close_1601_wib', universe_count: 1, stocks: [{ symbol: 'BBCA', quote_freshness_seconds: 30 }] }))
  await writeFile(verificationFile, JSON.stringify({ metrics: { evaluated: 4 } }))
  const base = await withServer(context, { FORECAST_FILE: forecastFile, VERIFICATION_FILE: verificationFile })
  const text = await (await fetch(`${base}/api/health`)).text(); const health = JSON.parse(text)
  assert.equal(health.ok, true); assert.equal(health.service, 'stock-analytics-dashboard')
  assert.equal(health.forecastSource.status, 'available'); assert.equal(health.latestSnapshot.status, 'available')
  assert.equal(health.verification.status, 'available'); assert.equal(health.dataQuality.universeCountConsistent, true)
  assert.equal(health.researchUpstream.status, 'not_checked'); assert.ok(Array.isArray(health.warnings)); assert.ok(health.generatedAt)
  assert.doesNotMatch(text, new RegExp(directory.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
})

test('Phase 14 health reports missing and stale artifacts explicitly', async (context) => {
  const directory = await mkdtemp(join(tmpdir(), 'stock-dashboard-phase14-'))
  const missingBase = await withServer(context, { FORECAST_FILE: join(directory, 'missing.json'), VERIFICATION_FILE: join(directory, 'missing-verification.json') })
  const missing = await (await fetch(`${missingBase}/api/health`)).json()
  assert.equal(missing.ok, true); assert.equal(missing.latestSnapshot.status, 'unavailable')
  assert.ok(missing.warnings.some(({ code }) => code === 'FORECAST_MISSING'))

  const forecastFile = join(directory, 'stale.json')
  await writeFile(forecastFile, JSON.stringify({ as_of: '2000-01-01T00:00:00Z', snapshot_slot: 'open_0901_wib', universe_count: 2, stocks: [{ symbol: 'BBCA', quote_freshness_seconds: 901 }] }))
  const staleBase = await withServer(context, { FORECAST_FILE: forecastFile, VERIFICATION_FILE: join(directory, 'none.json') })
  const stale = await (await fetch(`${staleBase}/api/health`)).json()
  assert.equal(stale.latestSnapshot.status, 'stale'); assert.equal(stale.dataQuality.staleQuoteCount, 1)
  assert.ok(stale.warnings.some(({ code }) => code === 'UNIVERSE_COUNT_MISMATCH'))
})
