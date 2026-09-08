'use strict';
/**
 * Methane MRV live console backend — a browser UI backed by the REAL OSDU platform.
 * Sibling of ccus-scep-deploy/live-frontend (separate console, separate port 8788).
 *
 * Holds the Keycloak credentials server-side, terminates the self-signed TLS, exposes
 * same-origin JSON: live Monitoring Plan state + version timeline, reconciliation, OGMP
 * report, attestation, evidence, live search — and ONE write action: apply a top-down
 * site rate, which re-reconciles against the bottom-up inventory (ISO 25624-1 11.3.1)
 * and drives the plan verified/suspended + the attestation on OSDU.
 *
 *   KC_SECRET_FILE=... KC_PASSWORD_FILE=... node server.js   ->  http://localhost:8788
 */
const http = require('http'); const https = require('https'); const fs = require('fs'); const path = require('path');
const { URL, URLSearchParams } = require('url');

const PORT = process.env.PORT || 8788;
const BASE = process.env.OSDU_BASE || 'https://172.171.6.4.nip.io';
const PARTITION = process.env.OSDU_PARTITION || 'osdu';
const KC = process.env.OSDU_KEYCLOAK || 'https://keycloak.172.171.6.4.nip.io/realms/osdu/protocol/openid-connect/token';
const CLIENT_ID = process.env.OSDU_CLIENT_ID || 'datafier'; const USERNAME = process.env.OSDU_USERNAME || 'aj@dveracity.com';
const SECRET_FILE = process.env.KC_SECRET_FILE, PASS_FILE = process.env.KC_PASSWORD_FILE;
const EXPORT = process.env.EXPORT_DIR || path.join(__dirname, '..', 'export');
const agent = new https.Agent({ rejectUnauthorized: false, keepAlive: true });
const W = (n) => `ofp:wks:work-product-component--${n}:1.0.0`;
const HOURS = 8760, GWP = 28;
const ACL = { owners: ['data.default.owners@osdu.group'], viewers: ['data.default.viewers@osdu.group'] };
const LEGAL = { legaltags: ['osdu-demo-legaltag'], otherRelevantDataCountries: ['US'], status: 'compliant' };

let tok = null;
async function token() {
  if (tok && Date.now() < tok.exp - 60000) return tok.v;
  if (!SECRET_FILE || !PASS_FILE) throw new Error('KC_SECRET_FILE and KC_PASSWORD_FILE must be set');
  const form = new URLSearchParams({ grant_type: 'password', client_id: CLIENT_ID,
    client_secret: fs.readFileSync(SECRET_FILE, 'utf8').replace(/[\r\n]+$/, ''), username: USERNAME,
    password: fs.readFileSync(PASS_FILE, 'utf8'), scope: 'openid' }).toString();
  const u = new URL(KC);
  const res = await new Promise((ok, no) => { const r = https.request({ method: 'POST', hostname: u.hostname, port: u.port || 443, path: u.pathname, agent,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(form) } },
    (rs) => { const c = []; rs.on('data', d => c.push(d)); rs.on('end', () => ok(Buffer.concat(c).toString())); }); r.on('error', no); r.write(form); r.end(); });
  const j = JSON.parse(res); if (!j.access_token) throw new Error('keycloak: ' + (j.error_description || j.error));
  tok = { v: j.access_token, exp: Date.now() + (j.expires_in || 300) * 1000 }; return tok.v;
}
async function osdu(method, p, body) {
  const t = await token(); const u = new URL(BASE + p); const payload = body ? Buffer.from(JSON.stringify(body)) : null;
  const headers = { Authorization: `Bearer ${t}`, 'data-partition-id': PARTITION, Accept: 'application/json' };
  if (payload) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = payload.length; }
  return new Promise((ok, no) => { const r = https.request({ method, hostname: u.hostname, port: u.port || 443, path: u.pathname + u.search, headers, agent },
    (rs) => { const c = []; rs.on('data', d => c.push(d)); rs.on('end', () => { const txt = Buffer.concat(c).toString(); let j = null; try { j = txt ? JSON.parse(txt) : null; } catch {} ok({ status: rs.statusCode, json: j, text: txt }); }); });
    r.on('error', no); r.setTimeout(30000, () => r.destroy(new Error('timeout'))); if (payload) r.write(payload); r.end(); });
}
const getRecord = (id) => osdu('GET', `/api/storage/v2/records/${encodeURIComponent(id)}`);
const putRecords = (recs) => osdu('PUT', '/api/storage/v2/records', recs);
const search = (kind, query, limit = 10) => osdu('POST', '/api/search/v2/query', query ? { kind, query, limit } : { kind, limit });
const rec = (kind, data) => ({ kind, acl: ACL, legal: LEGAL, data });
const baseAct = (t) => ({ activityType: t, dataSource: 'live-console', facilityId: 'MRV-01', recordingType: 'measured', sensitivity: 'confidential',
  reportingPeriodStart: '2025-01-01T00:00:00Z', reportingPeriodEnd: '2025-12-31T23:59:59Z' });

function summary() { try { return JSON.parse(fs.readFileSync(path.join(EXPORT, '_summary.json'), 'utf8')); } catch { return {}; } }

async function state() {
  const S = summary(); const R = S.records || {};
  const out = { base: BASE, partition: PARTITION, fetchedAt: new Date().toISOString(), site: S.site, year: S.year, evidence: [] };
  out.bottomUpKg = (S.restated && S.restated.bottomUp) || (S.metrics && S.metrics.bottom_up) || null;
  const planId = (R.plan || {}).id;
  if (planId) {
    const h = await getRecord(planId); const d = h.json?.data || {};
    out.plan = { id: planId, status: d.verificationStatus, hash: d.planHash, trigger: d.versionTrigger, version: h.json?.version,
      divergenceLimit: d.reconciliationDivergenceLimitPercent, coverageTarget: d.goldStandardCoveragePercent,
      materiality: d.materialityThresholdPercent, k: d.uncertaintyCoverageFactorK, reconciliationResultId: d.reconciliationResultId };
    const vr = await osdu('GET', `/api/storage/v2/records/versions/${encodeURIComponent(planId)}`);
    out.timeline = [];
    for (const v of (vr.json?.versions || [])) { const rv = await osdu('GET', `/api/storage/v2/records/${encodeURIComponent(planId)}/${v}`);
      out.timeline.push({ version: v, status: rv.json?.data?.verificationStatus, trigger: rv.json?.data?.versionTrigger }); }
    // latest reconciliation = the one the plan points at
    if (d.reconciliationResultId) { const rr = await getRecord(d.reconciliationResultId); out.reconciliation = { id: d.reconciliationResultId, data: rr.json?.data }; }
  }
  for (const [key, label] of [['attestation', 'attestation'], ['ogmp.v2', 'ogmp']]) { const id = (R[key] || {}).id; if (!id) continue;
    const r = await getRecord(id); out[label] = { id, data: r.json?.data }; }
  for (const [label, meta] of Object.entries(R)) {
    if (['plan', 'attestation', 'ogmp.v1', 'ogmp.v2', 'reconciliation.v1', 'reconciliation.v2'].includes(label)) continue;
    const r = await getRecord(meta.id); const kind = ((r.json?.kind || '').split('--')[1] || '').split(':')[0];
    out.evidence.push({ label, id: meta.id, kind, data: r.json?.data });
  }
  return out;
}

// Write action: apply a top-down site rate -> re-reconcile (ISO 11.3.1) -> drive plan + attestation.
async function setTopdown(rate) {
  const S = summary(); const R = S.records || {};
  const planId = R.plan.id, attId = (R.attestation || {}).id;
  const bottomUp = (S.restated && S.restated.bottomUp) || S.metrics.bottom_up;
  const head = (await getRecord(planId)).json; const d = head.data; const limit = d.reconciliationDivergenceLimitPercent || 20;
  const buInst = bottomUp / HOURS; const div = Math.abs(buInst - rate) / rate * 100; const pass = div <= limit;
  const target = pass ? 'verified' : 'suspended'; const log = [];
  await putRecords([rec(W('MethaneDetectionEvent'), { ...baseAct('ch4_detection'), deviceId: 'DRONE-CRDS-07', technology: 'drone',
    detectedConcentrationPPM: Math.round(rate / 4 * 10) / 10, windSpeedMPS: 3.8, windDirection: 248, ogmpLevel: 'level5', plumeSizeM2: Math.round(rate * 70) })]);
  await putRecords([rec(W('EmissionQuantification'), { ...baseAct('ch4_quantification'), sourceId: 'SITE', emissionRateKgPerHour: rate,
    quantificationMethod: 'massBalance', uncertaintyPercent: 24, co2eKg: Math.round(rate * HOURS * GWP), ogmpLevel: 'level5' })]);
  log.push(`top-down ${rate} kg/h stored`);
  const rr = await putRecords([rec(W('ReconciliationResult'), { ...baseAct('ch4_reconciliation'), bottomUpTotalKg: Math.round(bottomUp),
    topDownTotalKg: Math.round(rate * HOURS), divergencePercent: Math.round(div * 100) / 100,
    reconciliationVerdict: pass ? 'passed' : (div <= 30 ? 'marginal' : 'failed'), reconciledTotalKg: Math.round(bottomUp) })]);
  const reconId = rr.json.recordIds[0]; log.push(`reconciliation ${div.toFixed(1)}% → ${pass ? 'passed' : 'FAILED'}`);
  if (!pass) { await putRecords([rec(W('MethaneAlertEvent'), { ...baseAct('ch4_alert'), alertType: rate >= 100 ? 'superEmitter' : 'exceedance',
    thresholdValue: Math.round(buInst * (1 + limit / 100) * 10) / 10, measuredValue: rate, responseRequired: true })]); log.push('alert raised'); }
  const cur = d.verificationStatus;
  if (cur !== target) {
    await putRecords([{ kind: W('MethaneMonitoringPlan'), acl: ACL, legal: LEGAL, id: planId, data: { ...d, verificationStatus: target,
      versionTrigger: pass ? 'corrective' : 'eventDriven', reconciliationResultId: reconId } }]);
    if (attId) { const a = (await getRecord(attId)).json; await putRecords([{ kind: W('MethaneAttestation'), acl: ACL, legal: LEGAL, id: attId, data: {
      ...a.data, attestationStatus: pass ? 'reissued' : 'suspended', reconciliationResultId: reconId,
      reason: pass ? 'Re-issued: reconciliation passed on live re-survey' : 'Suspended: SiteLevelReconciliation failed on live re-survey',
      verifiableCredential: { ...a.data.verifiableCredential, credentialStatus: pass ? 'active' : 'suspended' } } }]); }
    log.push(`plan ${cur} → ${target}`, `attestation ${pass ? 'reissued' : 'suspended'}`);
  } else { await putRecords([{ kind: W('MethaneMonitoringPlan'), acl: ACL, legal: LEGAL, id: planId, data: { ...d, reconciliationResultId: reconId } }]); log.push(`plan stays ${cur}`); }
  return { applied: true, rate, divergence: div, target, transitioned: cur !== target, log };
}

const send = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
const body = (req) => new Promise(ok => { const c = []; req.on('data', d => c.push(d)); req.on('end', () => ok(Buffer.concat(c).toString())); });
http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, `http://localhost:${PORT}`);
    if (u.pathname === '/' || u.pathname === '/index.html') { res.writeHead(200, { 'Content-Type': 'text/html' }); return res.end(fs.readFileSync(path.join(__dirname, 'public', 'index.html'))); }
    if (u.pathname === '/api/health') { await token(); return send(res, 200, { ok: true, base: BASE, partition: PARTITION }); }
    if (u.pathname === '/api/state') return send(res, 200, await state());
    if (u.pathname === '/api/search' && req.method === 'POST') { const q = JSON.parse(await body(req) || '{}'); const r = await search(q.kind, q.query, q.limit || 10); return send(res, r.status, r.json); }
    if (u.pathname === '/api/methane/set-topdown' && req.method === 'POST') { const q = JSON.parse(await body(req) || '{}'); const v = parseFloat(q.rate);
      if (isNaN(v) || v <= 0) return send(res, 400, { error: 'rate (kg/h) > 0 required' }); return send(res, 200, await setTopdown(v)); }
    send(res, 404, { error: 'not found' });
  } catch (e) { send(res, 500, { error: String(e.message || e) }); }
}).listen(PORT, () => console.log(`Methane MRV live console on http://localhost:${PORT} → ${BASE} [${PARTITION}]`));
