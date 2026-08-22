#!/usr/bin/env node
// Arch Rogue keyboard-facing diagnostic: boots the built dist headless, walks
// with arrow keys (staggered diagonal release, like a human), then fires a
// bolt with key 2 and asserts the retained heading survives both the stop and
// the cast. Probes facing/aim ownership via ar_web_smoke_probe.
//
// Usage: node tools/web_input_probe.mjs [--browser flatpak|/path/to/chromium]
//        [--dist build/web/dist] [--port 8099]

import { spawn } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { launchPreset } from './web_cdp.mjs';

const args = process.argv.slice(2);
function argValue(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const dist = path.resolve(repoRoot, argValue('--dist', 'build/web/dist'));
const port = Number(argValue('--port', '8099'));
const browserName = argValue('--browser', process.env.AR_WEB_BROWSER || 'flatpak');
const baseUrl = `http://127.0.0.1:${port}/index.html`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function probe(page) {
  return JSON.parse(await page.evaluate('UTF8ToString(Module._ar_web_smoke_probe())'));
}
function facingOf(state) {
  return { x: state.facing_x, y: state.facing_y };
}
function close(a, b, eps = 0.05) {
  return Math.abs(a.x - b.x) <= eps && Math.abs(a.y - b.y) <= eps;
}
function show(tag, state) {
  console.log(`${tag}: facing=(${state.facing_x.toFixed(3)},${state.facing_y.toFixed(3)}) ` +
    `aim=(${state.aim_x.toFixed(3)},${state.aim_y.toFixed(3)}) aim_live=${state.aim_live} ` +
    `keyboard_aim=${state.keyboard_aim} bolt_cd=${state.bolt_cooldown} mode=${state.mode} modal=${state.modal_open}`);
}

const server = spawn('python3', [path.join(repoRoot, 'tools/web_serve.py'), '--root', dist, '--port', String(port)], {
  stdio: ['ignore', 'pipe', 'pipe'],
});
await sleep(800);

const browser = await launchPreset(browserName);
let failures = 0;
function record(name, ok, detail = '') {
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

try {
  const page = await browser.openPage();
  await page.setViewport(1280, 720);
  await page.navigate(baseUrl);
  await page.waitForConsole(/ARCH_ROGUE_READY/, { timeoutMs: 180000 });
  await page.waitFor('document.getElementById("ar-loading").hidden', { label: 'loading overlay hidden' });

  // Gesture (also the run's one deliberate mouse use), then start a run.
  await page.click(20, 700);
  await sleep(300);
  await page.key('n', 'KeyN', 78);
  await sleep(300);
  await page.key('Enter', 'Enter', 13);
  await page.waitFor('UTF8ToString(Module._ar_web_smoke_probe()).includes("\\"mode\\":\\"Playing\\"")',
    { timeoutMs: 20000, label: 'mode Playing' });

  // Dismiss the opening story modal (Enter advances/closes each page).
  for (let i = 0; i < 10; i += 1) {
    const state = await probe(page);
    if (!state.modal_open) break;
    await page.key('Enter', 'Enter', 13);
    await sleep(250);
  }
  record('modal-dismissed', !(await probe(page)).modal_open);

  // Walk screen-north-east: Up+Right held, then a human-style staggered
  // release (Right first, Up ~60ms later).
  await page.keyEvent('keydown', 'ArrowUp', 'ArrowUp', 38);
  await page.keyEvent('keydown', 'ArrowRight', 'ArrowRight', 39);
  await sleep(700);
  await page.keyEvent('keyup', 'ArrowRight', 'ArrowRight', 39);
  await sleep(60);
  await page.keyEvent('keyup', 'ArrowUp', 'ArrowUp', 38);
  await sleep(300);

  const stopped = await probe(page);
  show('after-stop', stopped);
  const heading = facingOf(stopped);
  record('keyboard-owns-aim', stopped.keyboard_aim === true, `keyboard_aim=${stopped.keyboard_aim}`);
  record('stop-heading-ne', close(heading, { x: 0, y: -1 }),
    `facing=(${heading.x.toFixed(3)},${heading.y.toFixed(3)}) want ~(0,-1)`);
  record('parked-cursor-aim-empty', Math.hypot(stopped.aim_x, stopped.aim_y) < 0.001,
    `aim=(${stopped.aim_x},${stopped.aim_y})`);

  // Fire a bolt with key 2; facing must not move.
  await page.key('2', 'Digit2', 50);
  await sleep(350);
  const fired = await probe(page);
  show('after-fire', fired);
  record('bolt-registered', fired.bolt_cooldown > 0, `bolt_cd=${fired.bolt_cooldown}`);
  record('fire-keeps-heading', close(facingOf(fired), heading),
    `facing=(${fired.facing_x.toFixed(3)},${fired.facing_y.toFixed(3)}) want (${heading.x.toFixed(3)},${heading.y.toFixed(3)})`);

  // Fire again while walking straight up: bolt should follow the new heading.
  await page.keyEvent('keydown', 'ArrowUp', 'ArrowUp', 38);
  await sleep(400);
  await page.keyEvent('keyup', 'ArrowUp', 'ArrowUp', 38);
  await sleep(250);
  const north = await probe(page);
  show('after-north-stop', north);
  record('retarget-north', close(facingOf(north), { x: -0.7071, y: -0.7071 }, 0.06),
    `facing=(${north.facing_x.toFixed(3)},${north.facing_y.toFixed(3)}) want ~(-0.707,-0.707)`);
} finally {
  try { await browser.close?.(); } catch {}
  try { browser.process?.kill(); } catch {}
  server.kill();
}

process.exit(failures === 0 ? 0 : 1);
