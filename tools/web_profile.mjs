#!/usr/bin/env node
// Deterministic crowded-floor web profiling at 1280x720 CSS after warmup,
// per the MX-web acceptance contract:
//   * bounded long-frame count — no frame interval above two 60 Hz vsync
//     periods (33.34 ms) after warmup (never a raw p95 frame-interval gate);
//   * measured per-frame sim+render CPU budget with headroom at 60 Hz
//     (main-thread busy p95 within AR_WEB_BUSY_BUDGET_MS, default 12.5 ms);
//   * clean console during the run;
//   * measured dynamic-heap use recorded against the pinned 256 MiB ceiling.
//
// The scenario reuses the desktop MX7 crowded-floor staging through URL
// parameters (seed 9707, warden, depth 8, theme 6) and the game's MX7_PERF /
// MX_WEB_PERF console reports, which also POST to the local server's /__report
// endpoint — so Chromium and Firefox are measured through one code path with
// no browser-automation protocol at all.
//
// Headless software-GL results are RELATIVE evidence: the gate verdict is
// reported, but only enforced (exit code) with --gate on a real-GPU run.
//
// Usage: node tools/web_profile.mjs [--browsers chromium,firefox] [--gate]
//        [--frames 600] [--warmup 120] [--port 8096] [--dist build/web/dist]

import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const args = process.argv.slice(2);
function argValue(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}
const gateEnforced = args.includes('--gate');
const frames = Number(argValue('--frames', '600'));
const warmup = Number(argValue('--warmup', '120'));
const port = Number(argValue('--port', '8096'));
const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const dist = path.resolve(repoRoot, argValue('--dist', 'build/web/dist'));
const evidenceDir = path.join(repoRoot, 'build/web/profile');
const busyBudgetMs = Number(process.env.AR_WEB_BUSY_BUDGET_MS || '12.5');
const browserList = argValue('--browsers', 'chromium,firefox').split(',');

const scenarioQuery =
  `?play=1&archetype=warden&depth=8&seed=9707&mx7_perf=1&theme=6&dark=0` +
  `&perf_frames=${frames}&perf_warmup=${warmup}&report=/__report`;
const url = `http://127.0.0.1:${port}/index.html${scenarioQuery}`;

function chromiumCommand() {
  if (process.env.AR_WEB_BROWSER && process.env.AR_WEB_BROWSER !== 'flatpak') {
    return { command: process.env.AR_WEB_BROWSER, prefix: [] };
  }
  return { command: 'flatpak', prefix: ['run', 'com.google.Chrome'] };
}

async function firefoxProfile() {
  const profile = `/tmp/ar-ff-profile-${process.pid}-${Date.now()}`;
  await mkdir(profile, { recursive: true });
  await writeFile(path.join(profile, 'user.js'), [
    'user_pref("webgl.force-enabled", true);',
    'user_pref("webgl.disabled", false);',
    'user_pref("gfx.webrender.software", true);',
    'user_pref("media.autoplay.default", 0);',
    'user_pref("browser.shell.checkDefaultBrowser", false);',
    'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
    'user_pref("app.update.disabledForTesting", true);',
    'user_pref("browser.sessionstore.resume_from_crash", false);',
  ].join('\n'));
  return profile;
}

function browserSpawn(name, firefoxProfileDir) {
  if (name === 'firefox') {
    return spawn('firefox', ['--headless', '--no-remote', '--profile', firefoxProfileDir,
      '--window-size', '1280,720', url], { stdio: 'ignore' });
  }
  const { command, prefix } = chromiumCommand();
  return spawn(command, [...prefix,
    '--headless=new', '--enable-unsafe-swiftshader', '--no-first-run',
    '--no-default-browser-check', `--user-data-dir=/tmp/ar-prof-${process.pid}-${Date.now()}`,
    '--window-size=1280,720', '--disable-background-timer-throttling', url,
  ], { stdio: 'ignore' });
}

// The local server prints every /__report POST as "web-serve-report: <line>".
const server = spawn('python3', [path.join(repoRoot, 'tools/web_serve.py'), '--root', dist, '--port', String(port)], {
  stdio: ['ignore', 'pipe', 'pipe'],
});
const reportLines = [];
server.stdout.on('data', (chunk) => {
  for (const line of chunk.toString().split('\n')) {
    if (line.startsWith('web-serve-report: ')) {
      reportLines.push(line.slice('web-serve-report: '.length));
    }
  }
});
await new Promise((resolve) => setTimeout(resolve, 800));

function takeReports(startIndex) {
  const found = {};
  for (let i = startIndex; i < reportLines.length; i++) {
    const line = reportLines[i];
    const space = line.indexOf(' ');
    const tag = line.slice(0, space);
    try { found[tag] = JSON.parse(line.slice(space + 1)); } catch { /* skip */ }
  }
  return found;
}

const runs = [];
let anyGateFailure = false;

for (const name of browserList) {
  const start = reportLines.length;
  console.log(`web-profile: running ${name} — ${frames} frames after ${warmup} warmup at 1280x720 CSS`);
  const firefoxProfileDir = name === 'firefox' ? await firefoxProfile() : null;
  const browser = browserSpawn(name, firefoxProfileDir);
  const deadline = Date.now() + 8 * 60 * 1000;
  let reports = {};
  for (;;) {
    reports = takeReports(start);
    if (reports.MX7_PERF && reports.MX_WEB_PERF && reports.MX_WEB_DONE) break;
    if (Date.now() > deadline) break;
    if (browser.exitCode !== null && !(reports.MX7_PERF && reports.MX_WEB_PERF)) break;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  browser.kill('SIGTERM');
  await new Promise((resolve) => setTimeout(resolve, 500));
  browser.kill('SIGKILL');

  if (!reports.MX7_PERF || !reports.MX_WEB_PERF) {
    console.log(`web-profile: ${name}: FAILED — no perf reports received`);
    runs.push({ browser: name, ok: false, error: 'no reports' });
    anyGateFailure = true;
    continue;
  }
  const frameReport = reports.MX7_PERF;
  const busyReport = reports.MX_WEB_PERF;
  const done = reports.MX_WEB_DONE || { errors: -1, warnings: -1 };
  const heapMiB = busyReport.heap_dynamic_bytes / (1024 * 1024);
  const gate = {
    long_frames_ok: frameReport.long_frames_33ms === 0,
    busy_budget_ok: busyReport.busy_p95_ms <= busyBudgetMs,
    resources_ok: frameReport.resources_ready === true,
    console_ok: done.errors === 0,
  };
  const gateOk = Object.values(gate).every(Boolean);
  anyGateFailure = anyGateFailure || !gateOk;
  runs.push({ browser: name, ok: true, gateOk, gate, frameReport, busyReport, consoleDefects: done });
  console.log(`web-profile: ${name}: frame mean ${frameReport.mean_ms.toFixed(2)}ms p95 ${frameReport.p95_ms.toFixed(2)}ms, ` +
    `long frames(>33.34ms) ${frameReport.long_frames_33ms}/${frameReport.frames}`);
  console.log(`web-profile: ${name}: busy mean ${busyReport.busy_mean_ms.toFixed(2)}ms p95 ${busyReport.busy_p95_ms.toFixed(2)}ms ` +
    `(budget ${busyBudgetMs}ms), heap ${heapMiB.toFixed(1)} MiB of 256 MiB pinned, temp arena peak ${(busyReport.temp_arena_high_mark/1048576).toFixed(1)} MiB`);
  console.log(`web-profile: ${name}: console errors ${done.errors}, warnings ${done.warnings}; gate ${gateOk ? 'PASS' : 'MISS'} ` +
    `${gateEnforced ? '(enforced)' : '(report-only: headless software GL is relative evidence)'}`);
}

server.kill();
await mkdir(evidenceDir, { recursive: true });
await writeFile(path.join(evidenceDir, 'profile-report.json'), JSON.stringify({
  when: new Date().toISOString(),
  url,
  frames, warmup, busyBudgetMs,
  gateEnforced,
  runs,
}, null, 2));
console.log(`web-profile: evidence written to build/web/profile/profile-report.json`);
process.exit(gateEnforced && anyGateFailure ? 1 : 0);
