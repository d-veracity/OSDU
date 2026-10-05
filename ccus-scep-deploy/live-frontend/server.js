'use strict';
/**
 * Live SCEP console backend — serves a browser UI backed by the REAL OSDU platform.
 *
 * Why a backend: a browser can't talk to the cimpl-stack directly (self-signed CA,
 * Keycloak auth, no CORS). This tiny Node server holds the service credentials, mints/
 * refreshes the Keycloak token, terminates the self-signed TLS, and exposes same-origin
 * JSON endpoints the UI can call. Pure Node stdlib — no dependencies.
 *
 * Secrets stay OUT of the repo: read from the scratchpad files, never sent to the browser.
 *
 *   KC_SECRET_FILE=... KC_PASSWORD_FILE=... node server.js
 *   -> open http://localhost:8787
 */
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { URL, URLSearchParams } = require('url');

const PORT = process.env.PORT || 8787;
const BASE = process.env.OSDU_BASE || 'https://172.171.6.4.nip.io';
const PARTITION = process.env.OSDU_PARTITION || 'osdu';
const KC = process.env.OSDU_KEYCLOAK || 'https://keycloak.172.171.6.4.nip.io/realms/osdu/protocol/openid-connect/token';
const CLIENT_ID = process.env.OSDU_CLIENT_ID || 'datafier';
const USERNAME = process.env.OSDU_USERNAME || 'aj@dveracity.com';
const SECRET_FILE = process.env.KC_SECRET_FILE;
const PASS_FILE = process.env.KC_PASSWORD_FILE;
const EXPORT = process.env.EXPORT_DIR || path.join(__dirname, '..', 'export');
const agent = new https.Agent({ rejectUnauthorized: false, keepAlive: true });
const K = (n) => `ofp:wks:work-product-component--${n}:1.0.0`;

/* ---- Keycloak token (cached) ---- */
let tok = null;
async function token() {
  if (tok && Date.now() < tok.exp - 60000) return tok.v;
  if (!SECRET_FILE || !PASS_FILE) throw new Error('KC_SECRET_FILE and KC_PASSWORD_FILE must be set');
  const form = new URLSearchParams({ grant_type: 'password', client_id: CLIENT_ID,
    client_secret: fs.readFileSync(SECRET_FILE, 'utf8').replace(/[\r\n]+$/, ''),
    username: USERNAME, password: fs.readFileSync(PASS_FILE, 'utf8'), scope: 'openid' }).toString();
  const u = new URL(KC);
  const res = await new Promise((ok, no) => {
    const r = https.request({ method: 'POST', hostname: u.hostname, port: u.port || 443, path: u.pathname, agent,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(form) } },
      (rs) => { const c = []; rs.on('data', d => c.push(d)); rs.on('end', () => ok(Buffer.concat(c).toString())); });
    r.on('error', no); r.write(form); r.end();
  });
  const j = JSON.parse(res);
  if (!j.access_token) throw new Error('keycloak: ' + (j.error_description || j.error || 'no token'));
  tok = { v: j.access_token, exp: Date.now() + (j.expires_in || 300) * 1000 };
  return tok.v;
}

/* ---- OSDU calls ---- */
async function osdu(method, apipath, body) {
  const t = await token();
  const u = new URL(BASE + apipath);
  const payload = body ? Buffer.from(JSON.stringify(body)) : null;
  const headers = { Authorization: `Bearer ${t}`, 'data-partition-id': PARTITION, Accept: 'application/json' };
  if (payload) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = payload.length; }
  return new Promise((ok, no) => {
    const r = https.request({ method, hostname: u.hostname, port: u.port || 443, path: u.pathname + u.search, headers, agent },
      (rs) => { const c = []; rs.on('data', d => c.push(d)); rs.on('end', () => {
        const txt = Buffer.concat(c).toString(); let j = null; try { j = txt ? JSON.parse(txt) : null; } catch {}
        ok({ status: rs.statusCode, json: j, text: txt }); }); });
    r.on('error', no); r.setTimeout(30000, () => r.destroy(new Error('timeout')));
    if (payload) r.write(payload); r.end();
  });
}
const getRecord = (id) => osdu('GET', `/api/storage/v2/records/${encodeURIComponent(id)}`);
const search = (kind, query, limit = 10) => osdu('POST', '/api/search/v2/query', query ? { kind, query, limit } : { kind, limit });

/* ---- live write actions: drive the SCEP through certified/suspended on OSDU ---- */
const AOR = 30;
const ACL = { owners: ['data.default.owners@osdu.group'], viewers: ['data.default.viewers@osdu.group'] };
const LEGAL = { legaltags: ['osdu-demo-legaltag'], otherRelevantDataCountries: ['US'], status: 'compliant' };
const putRecords = (records) => osdu('PUT', '/api/storage/v2/records', records);
const baseAct = (t) => ({ activityType: t, dataSource: 'live-console', facilityId: 'CCS1-Decatur-ClassVI',
  recordingType: 'measured', sensitivity: 'confidential',
  reportingPeriodStart: '2011-11-01T00:00:00Z', reportingPeriodEnd: '2014-11-30T23:59:59Z' });

// Apply a monitored plume extent to OSDU and transition the SCEP + claim + attestation.
async function setPlume(extent) {
  const ids = loadIds();
  const scepId = (ids['scep.snapshot'] || {}).id;
  const attId = (ids['attestation'] || {}).id;
  const claimId = (ids['anomaly.claimAdjust'] || {}).id;
  const storageId = (ids['evidence.storage'] || {}).id; // the stable "current conditions" record
  const breach = extent > AOR;
  const target = breach ? 'suspended' : 'certified';
  const log = [];

  // 1) record a new plume observation (append-only evidence)
  await putRecords([{ kind: K('CO2PlumeObservation'), acl: ACL, legal: LEGAL, data: {
    ...baseAct('plume_observation'), observationMethod: 'seismic', lateralExtentKm2: extent,
    migrationRateMPerYear: breach ? 640 : 210, depthM: 2130, modelComparisonScore: breach ? 0.41 : 0.86 } }]);
  log.push(`plume observation ${extent} km² stored`);

  // 2) update the current-conditions storage record (stable id → new OSDU version)
  if (storageId) {
    const s = (await getRecord(storageId)).json;
    await putRecords([{ kind: K('CO2StorageRecord'), acl: ACL, legal: LEGAL, id: storageId, data: {
      ...s.data, plumeExtentKm2: extent, leakageRateKgPerYear: breach ? 21000 : 4,
      containmentStatus: breach ? 'breached' : 'stabilized' } }]);
  }

  // 3) transition the SCEP + claim + attestation only if the status changes
  const head = (await getRecord(scepId)).json;
  const cur = head.data.certificationStatusAtSnapshot;
  if (cur !== target) {
    await putRecords([{ kind: K('MMVEventRecord'), acl: ACL, legal: LEGAL, data: {
      ...baseAct('mmv_event'), eventType: breach ? 'reassessment_trigger' : 'recertification',
      deviationFromBaseline: Math.round((extent - 7.8) / 7.8 * 100), correctiveActionRequired: breach,
      scepVersionAffected: 'live' } }]);
    await putRecords([{ kind: K('SCEPVersionSnapshot'), acl: ACL, legal: LEGAL, id: scepId, data: {
      ...head.data, certificationStatusAtSnapshot: target, versionTrigger: breach ? 'eventDriven' : 'corrective' } }]);
    if (claimId) { const c = (await getRecord(claimId)).json; await putRecords([{ kind: K('CarbonClaimAdjustmentRecord'),
      acl: ACL, legal: LEGAL, id: claimId, data: { ...c.data, adjustedClaimTonnes: breach ? 950000 : 985000,
      claimStatus: breach ? 'adjusted' : 'active',
      adjustmentReason: breach ? `AoR exceedance — plume ${extent} km² > ${AOR} km²` : 'Re-certified — plume within AoR' } }]); }
    if (attId) { const a = (await getRecord(attId)).json; await putRecords([{ kind: K('SCEPAttestation'),
      acl: ACL, legal: LEGAL, id: attId, data: { ...a.data, attestationStatus: breach ? 'suspended' : 'issued',
      reason: breach ? 'SCEP suspended on plume breach' : 'Re-issued on re-certification',
      verifiableCredential: { ...a.data.verifiableCredential, credentialStatus: breach ? 'suspended' : 'active' } } }]); }
    log.push(`SCEP ${cur} → ${target}`, `claim ${breach ? '985k→950k' : '→985k'}`, `attestation ${breach ? 'suspended' : 'issued'}`);
  } else {
    log.push(`SCEP already ${cur} — no transition`);
  }
  return { applied: true, extent, target, transitioned: cur !== target, log };
}

/* ---- aggregate live SCEP state ---- */
function loadIds() {
  try { return JSON.parse(fs.readFileSync(path.join(EXPORT, '_summary.json'), 'utf8')).records || {}; }
  catch { return {}; }
}
async function scepState() {
  const ids = loadIds();
  const out = { base: BASE, partition: PARTITION, fetchedAt: new Date().toISOString(), evidence: [] };

  // SCEP snapshot (live head + full version timeline)
  const scepId = (ids['scep.snapshot'] || {}).id;
  if (scepId) {
    const head = await getRecord(scepId);
    out.scep = { id: scepId, status: head.json?.data?.certificationStatusAtSnapshot,
      version: head.json?.version, hash: head.json?.data?.snapshotHash,
      trigger: head.json?.data?.versionTrigger };
    const vr = await osdu('GET', `/api/storage/v2/records/versions/${encodeURIComponent(scepId)}`);
    const versions = vr.json?.versions || [];
    out.timeline = [];
    for (const v of versions) {
      const rv = await osdu('GET', `/api/storage/v2/records/${encodeURIComponent(scepId)}/${v}`);
      out.timeline.push({ version: v, status: rv.json?.data?.certificationStatusAtSnapshot, trigger: rv.json?.data?.versionTrigger });
    }
  }
  // attestation + claim (live)
  for (const [key, label] of [['attestation', 'attestation'], ['anomaly.claimAdjust', 'claim']]) {
    const id = (ids[key] || {}).id; if (!id) continue;
    const r = await getRecord(id); out[label] = { id, data: r.json?.data };
  }
  // evidence list (live GET of each)
  for (const [label, meta] of Object.entries(ids)) {
    if (!label.startsWith('evidence.') && !label.startsWith('anomaly.breachPlume') && !label.startsWith('ofp.')) continue;
    const r = await getRecord(meta.id);
    const kind = ((r.json?.kind || '').split('--')[1] || '').split(':')[0];
    out.evidence.push({ label, id: meta.id, kind, data: r.json?.data });
  }
  return out;
}

/* ---- HTTP server ---- */
const send = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, `http://localhost:${PORT}`);
    if (u.pathname === '/' || u.pathname === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(fs.readFileSync(path.join(__dirname, 'public', 'index.html')));
    }
    if (u.pathname === '/api/health') { await token(); return send(res, 200, { ok: true, base: BASE, partition: PARTITION }); }
    if (u.pathname === '/api/state') return send(res, 200, await scepState());
    if (u.pathname === '/api/record') { const r = await getRecord(u.searchParams.get('id')); return send(res, r.status, r.json); }
    if (u.pathname === '/api/search' && req.method === 'POST') {
      const b = await new Promise(ok => { const c = []; req.on('data', d => c.push(d)); req.on('end', () => ok(Buffer.concat(c).toString())); });
      const q = JSON.parse(b || '{}'); const r = await search(q.kind, q.query, q.limit || 10); return send(res, r.status, r.json);
    }
    if (u.pathname === '/api/scep/set-plume' && req.method === 'POST') {
      const b = await new Promise(ok => { const c = []; req.on('data', d => c.push(d)); req.on('end', () => ok(Buffer.concat(c).toString())); });
      const q = JSON.parse(b || '{}'); const ext = parseFloat(q.extent);
      if (isNaN(ext)) return send(res, 400, { error: 'extent (km²) required' });
      return send(res, 200, await setPlume(ext));
    }
    send(res, 404, { error: 'not found' });
  } catch (e) { send(res, 500, { error: String(e.message || e) }); }
});
server.listen(PORT, () => console.log(`SCEP live console on http://localhost:${PORT}  → ${BASE} [${PARTITION}]`));
