#!/usr/bin/env node
// Arch Rogue web smoke: boots the built dist in a headless Chromium-family
// browser over CDP and validates the milestone smoke surface: boot, clean
// console, audio unlock via a trusted gesture, opening story modal, bounded
// lazy pack materialization/adoption, lifecycle checkpointing, save/reload
// continuity, tmp/bak recovery of a
// corrupted primary save, resize, fullscreen, synthetic controller exposure,
// and cached reload. Evidence lands under build/web/smoke/.
//
// Usage: node tools/web_smoke.mjs [--browser flatpak|/path/to/chromium]
//        [--dist build/web/dist] [--entry-path /index.html] [--port 8097]

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
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
const entryPath = argValue('--entry-path', '/index.html');
if (!entryPath.startsWith('/') || entryPath.includes('..')) {
  throw new Error('--entry-path must be an absolute site path without traversal');
}
const port = Number(argValue('--port', '8097'));
const browserName = argValue('--browser', process.env.AR_WEB_BROWSER || 'flatpak');
const evidenceDir = path.join(repoRoot, 'build/web/smoke');
const baseUrl = `http://127.0.0.1:${port}${entryPath}`;

// Environment-dependent driver chatter that is not an application defect:
// headless screenshot readback and software-GL performance notes.
const CONSOLE_ALLOWLIST = [
  /GL Driver Message.*Performance/,
  /Automatic fallback to software WebGL/,
  // Upstream raylib/miniaudio still uses the deprecated ScriptProcessorNode
  // Web Audio path; tracked as an upstream limitation, not an app defect.
  /ScriptProcessorNode is deprecated/,
  // Headless smoke clicks carry no real user activation, so the fullscreen
  // request logs a gesture warning; real user clicks do not.
  /requestFullscreen.*user gesture/,
];

const results = [];
let currentPage = null;

function record(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
}

async function probe(page) {
  return JSON.parse(await page.evaluate('UTF8ToString(Module._ar_web_smoke_probe())'));
}

function consoleDefects(page) {
  const bad = page.sessionConsoleLines.filter((line) =>
    (line.type === 'error' || line.type === 'warning') &&
    !CONSOLE_ALLOWLIST.some((pattern) => pattern.test(line.text)));
  return bad.concat(page.sessionPageErrors.map((text) => ({ type: 'pageerror', text })));
}

async function bootPage(browser, query = '') {
  const page = await browser.openPage();
  currentPage = page;
  await page.setViewport(1280, 720);
  await page.navigate(baseUrl + query);
  await page.waitForConsole(/ARCH_ROGUE_READY/, { timeoutMs: 180000 });
  await page.waitFor('document.getElementById("ar-loading").hidden', { label: 'loading overlay hidden' });
  return page;
}

const server = spawn('python3', [path.join(repoRoot, 'tools/web_serve.py'), '--root', dist, '--port', String(port)], {
  stdio: ['ignore', 'pipe', 'pipe'],
});
await new Promise((resolve) => setTimeout(resolve, 800));

const browser = await launchPreset(browserName);
try {
  await mkdir(evidenceDir, { recursive: true });

  // --- boot + clean console -------------------------------------------------
  let page = await bootPage(browser);
  let state = await probe(page);
  record('boot', ['Title', 'Story_Decision'].includes(state.mode) && state.storage_ready && state.hydrated,
    `mode=${state.mode} storage=${state.storage_ready}`);
  record('boot-audio-deferred', state.audio_ready === false, 'audio must wait for a gesture');

  // --- audio unlock via trusted gesture ------------------------------------
  await page.click(20, 700);
  await new Promise((resolve) => setTimeout(resolve, 400));
  state = await probe(page);
  record('audio-unlock', state.audio_ready === true, `audio_ready=${state.audio_ready}`);
  record('music-boot-intro', state.music_mix === 'menu_boot' && state.music_streams === 1 &&
    state.music_layers === 1 && state.music_callbacks > 0,
    `mix=${state.music_mix} streams=${state.music_streams} layers=${state.music_layers} callbacks=${state.music_callbacks} phase=${state.music_phase_ms} heap=${(state.heap_dynamic_bytes / (1024 * 1024)).toFixed(1)}MiB`);
  record('music-stream-stable', state.music_recoveries === 0,
    `recoveries=${state.music_recoveries}`);

  // Fresh alpha.26+ profiles ask about narrative before the title. Keep Yes
  // so the opening-story and save/resume checks below exercise their fixtures.
  if (state.mode === 'Story_Decision') {
    await page.key('Enter', 'Enter', 13);
    await new Promise((resolve) => setTimeout(resolve, 300));
    await page.key('Enter', 'Enter', 13); // skip the recorded-choice farewell
    await page.waitFor('JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).mode === "Title"',
      { timeoutMs: 10000, label: 'title after first-boot story choice' });
    record('first-boot-story-choice', true, 'accepted narrative and reached Title');
  }

  // --- start a run; lazy packs stream and adopt -----------------------------
  await page.key('n', 'KeyN', 78); // Title hotkey: New Run -> Select
  await new Promise((resolve) => setTimeout(resolve, 300));
  await page.key('Enter', 'Enter', 13); // Select -> Playing
  await page.waitFor('UTF8ToString(Module._ar_web_smoke_probe()).includes("\\"mode\\":\\"Playing\\"")',
    { timeoutMs: 20000, label: 'mode Playing' });
  state = await probe(page);
  record('run-start', state.run_active && state.mode === 'Playing', `depth=${state.depth}`);
  record('opening-story-modal', state.modal_open === true,
    `modal_open=${state.modal_open} audio_playing=${state.audio_playing}`);
  // The 9.6 s boot intro ignores the selector until its boundary, so shortly
  // after run start the director is either still in the intro or already on
  // the menu mix selected by the opening story modal.
  record('music-selector-follows-run', state.music_mix === 'menu_boot' || state.music_mix === 'menu',
    `mix=${state.music_mix}`);
  const packDeadline = Date.now() + 180000;
  let residentSeen = 0;
  while (Date.now() < packDeadline) {
    residentSeen = page.consoleLines.filter((l) => /ARCH_ROGUE_WEB_PACK resident/.test(l.text)).length;
    if (residentSeen >= 3) break;
    if (page.consoleLines.some((l) => /ARCH_ROGUE_WEB_PACK failed/.test(l.text))) break;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  state = await probe(page);
  record('lazy-packs', state.packs_resident >= 3,
    `resident=${state.packs_resident} adopting=${state.packs_adopting}`);

  // --- play a little, then lifecycle checkpoint ----------------------------
  await page.keyEvent('keydown', 'ArrowRight', 'ArrowRight', 39);
  await new Promise((resolve) => setTimeout(resolve, 900));
  await page.keyEvent('keyup', 'ArrowRight', 'ArrowRight', 39);
  await page.evaluate('Module._ar_web_set_visible(0); true');
  const checkpoint = await page.waitForConsole(/ARCH_ROGUE_SUSPEND_CHECKPOINT/, { timeoutMs: 5000 });
  await page.evaluate('Module._ar_web_set_visible(1); true');
  record('suspend-checkpoint', /durable=true/.test(checkpoint.text), checkpoint.text);
  await page.waitFor('Module.arStorageStats ? Module.arStorageStats().pending === 0 : true',
    { timeoutMs: 10000, label: 'IndexedDB writes settled' });

  // --- save/reload continuity ----------------------------------------------
  const depthBefore = (await probe(page)).depth;
  await page.screenshot(path.join(evidenceDir, 'smoke-playing.png'));
  await page.navigate(baseUrl);
  await page.waitForConsole(/ARCH_ROGUE_READY/, { timeoutMs: 120000 });
  state = await probe(page);
  record('reload-resume-available', state.resume_available === true,
    `resume_available=${state.resume_available}`);
  // Resume: Title row R hotkey -> Resume_Veil -> confirm.
  await page.key('r', 'KeyR', 82);
  await page.waitFor('UTF8ToString(Module._ar_web_smoke_probe()).includes("Resume_Veil")',
    { timeoutMs: 15000, label: 'resume veil' });
  await page.key('Enter', 'Enter', 13);
  await page.waitFor('UTF8ToString(Module._ar_web_smoke_probe()).includes("\\"mode\\":\\"Playing\\"")',
    { timeoutMs: 15000, label: 'resumed to Playing' });
  state = await probe(page);
  record('save-reload', state.run_active && state.depth === depthBefore,
    `depth ${state.depth} == ${depthBefore}`);

  // --- recovery: corrupt the primary document; .bak must win ---------------
  await page.evaluate('Module._ar_web_set_visible(0); Module._ar_web_set_visible(1); true');
  await page.waitFor('Module.arStorageStats ? Module.arStorageStats().pending === 0 : true',
    { timeoutMs: 10000, label: 'writes settled before corruption' });
  const corrupted = await page.evaluate(`new Promise((resolve) => {
    const open = indexedDB.open('arch-rogue-save', 1);
    open.onsuccess = (event) => {
      const db = event.target.result;
      const tx = db.transaction('kv', 'readwrite');
      const store = tx.objectStore('kv');
      const has = store.getKey('/save/run.json.bak');
      has.onsuccess = () => {
        if (!has.result) { db.close(); resolve('no-bak'); return; }
        store.put(new Uint8Array([0x7b, 0x22, 0x58]), '/save/run.json');
        tx.oncomplete = () => { db.close(); resolve('ok'); };
        tx.onerror = () => { db.close(); resolve('tx-error'); };
      };
      has.onerror = () => { db.close(); resolve('probe-error'); };
    };
    open.onerror = () => resolve('open-error');
  })`);
  if (corrupted !== 'ok') {
    record('recovery', false, `could not stage corruption: ${corrupted}`);
  } else {
    await page.navigate(baseUrl);
    await page.waitForConsole(/ARCH_ROGUE_READY/, { timeoutMs: 120000 });
    state = await probe(page);
    record('recovery', state.resume_available === true,
      `bak promoted, resume_available=${state.resume_available}`);
  }

  // --- resize: drive the real pipeline (viewport -> ResizeObserver -> game) --
  await page.setViewport(1024, 600);
  await page.waitFor('UTF8ToString(Module._ar_web_smoke_probe()).includes("\\"screen_w\\":1024")',
    { timeoutMs: 8000, label: 'resize applied' }).catch(() => {});
  state = await probe(page);
  record('resize', state.screen_w === 1024 && state.screen_h === 600,
    `screen=${state.screen_w}x${state.screen_h}`);
  await page.setViewport(1280, 720);
  await new Promise((resolve) => setTimeout(resolve, 500));

  // --- fullscreen request (trusted click on the shell button) ---------------
  const fullscreenErrorsBefore = page.pageErrors.length;
  await page.evaluate('document.getElementById("ar-fullscreen").hidden = false; true');
  const rect = await page.evaluate(`(() => {
    const r = document.getElementById('ar-fullscreen').getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
  })()`);
  await page.click(rect.x, rect.y);
  await new Promise((resolve) => setTimeout(resolve, 500));
  record('fullscreen-click', page.pageErrors.length === fullscreenErrorsBefore,
    'no page errors from fullscreen request');

  // --- cached reload (upgrade path relies on content-addressed names) ------
  await page.navigate(baseUrl);
  await page.waitForConsole(/ARCH_ROGUE_READY/, { timeoutMs: 120000 });
  const cached = await page.evaluate(`performance.getEntriesByType('resource')
    .filter((entry) => /archrogue-[0-9a-f]{12}\\./.test(entry.name))
    .map((entry) => ({ name: entry.name.split('/').pop(), transferSize: entry.transferSize }))`);
  const cachedHits = cached.filter((entry) => entry.transferSize === 0).length;
  record('cached-reload', cached.length >= 2 && cachedHits >= 1,
    `${cachedHits}/${cached.length} immutable files served from cache`);

  // --- synthetic controller exposure ---------------------------------------
  // Runs last: overriding navigator.getGamepads poisons emscripten's GLFW
  // keyboard routing for the rest of the page's life (harness artifact),
  // so every keyboard-driven scenario must already be complete.
  await page.evaluate(`(() => {
    const pad = {
      id: 'ar-smoke-pad', index: 0, connected: true, mapping: 'standard',
      timestamp: performance.now(),
      axes: [0, 0, 0, 0],
      buttons: Array.from({ length: 17 }, () => ({ pressed: false, touched: false, value: 0 })),
    };
    window.__arSmokePad = pad;
    navigator.getGamepads = () => [pad];
    const ev = new Event('gamepadconnected');
    Object.defineProperty(ev, 'gamepad', { value: pad });
    window.dispatchEvent(ev);
    return true;
  })()`);
  await new Promise((resolve) => setTimeout(resolve, 600));
  state = await probe(page);
  record('controller-visible', state.gamepad === true, `gamepad=${state.gamepad}`);

  // Stadia and other browser-standard pads expose LT/RT as buttons 6/7 with
  // only four stick axes. Exercise that exact shape rather than six-axis input.
  await page.evaluate(`(() => {
    const pad = window.__arSmokePad;
    pad.buttons[6] = { pressed: true, touched: true, value: 1 };
    pad.buttons[7] = { pressed: true, touched: true, value: 1 };
    pad.timestamp = performance.now();
  })()`);
  await new Promise((resolve) => setTimeout(resolve, 120));
  state = await probe(page);
  record('controller-button-triggers', state.left_trigger === true && state.right_trigger === true,
    `lt=${state.left_trigger} rt=${state.right_trigger} axes=4`);

  // --- clean console across the whole session ------------------------------
  const defects = consoleDefects(page);
  record('clean-console', defects.length === 0,
    defects.slice(0, 3).map((d) => `${d.type}: ${d.text.slice(0, 120)}`).join(' | ') || 'no defects');

  await page.screenshot(path.join(evidenceDir, 'smoke-final.png'));

  // --- co-op: host a room against a local relay -----------------------------
  // Title -> Co-op -> Host -> consent must reach the lobby with a clean
  // console. The 2026-10-11 regression (temp-arena misalignment panicking in
  // the JSON parser's map) only showed up on this path.
  const relayBinary = path.join(repoRoot, 'build/archrogue_relay');
  if (!existsSync(relayBinary)) {
    record('coop-host-lobby', false, 'build/archrogue_relay missing; run ./build.sh relay');
  } else {
    const relayPort = port + 1;
    const relay = spawn(relayBinary, ['--port', String(relayPort), '--origins', `http://127.0.0.1:${port}`], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      page = await bootPage(browser, `?relay=${encodeURIComponent(`ws://127.0.0.1:${relayPort}/mp`)}`);
      await page.click(20, 700);
      await new Promise((resolve) => setTimeout(resolve, 300));
      await page.waitFor('JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).mode === "Title"',
        { timeoutMs: 10000, label: 'title before co-op' });
      for (const key of ['ArrowDown', 'Enter', 'Enter', 'Enter']) { // Co-op row, Host, accept consent
        await page.key(key, key, key === 'Enter' ? 13 : 40);
        await new Promise((resolve) => setTimeout(resolve, 350));
      }
      await page.waitFor('JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).mode === "Coop_Lobby"',
        { timeoutMs: 15000, label: 'co-op lobby after hosting' });
      const coopDefects = consoleDefects(page);
      record('coop-host-lobby', coopDefects.length === 0,
        coopDefects.slice(0, 3).map((d) => `${d.type}: ${d.text.slice(0, 160)}`).join(' | ') || 'hosted a room, lobby reached, no defects');

      // --- co-op: join a native bot host; the partner's archetype pack must
      // stream in and activate (2026-10-11: the partner drew as a fallback
      // disc because only the local archetype adopted its pack) -------------
      const botBinary = path.join(repoRoot, 'build/coop_bot');
      if (!existsSync(botBinary)) {
        record('coop-join-partner-sprite', false,
          'build/coop_bot missing; run: odin build tools/coop_bot.odin -file -out:build/coop_bot -vet');
      } else {
        const codeFile = path.join(evidenceDir, 'coop-code');
        await rm(codeFile, { force: true });
        const bot = spawn(botBinary, ['--role', 'host', '--url', `ws://127.0.0.1:${relayPort}/mp`,
          '--code-file', codeFile, '--seconds', '120', '--script', 'idle', '--archetype', 'Rogue'], {
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        try {
          let code = '';
          for (let i = 0; i < 60 && code.length !== 4; i += 1) {
            await new Promise((resolve) => setTimeout(resolve, 250));
            try { code = (await readFile(codeFile, 'utf8')).trim(); } catch { code = ''; }
          }
          if (code.length !== 4) throw new Error('bot host published no room code');
          page = await bootPage(browser, `?relay=${encodeURIComponent(`ws://127.0.0.1:${relayPort}/mp`)}`);
          await page.click(20, 700);
          await new Promise((resolve) => setTimeout(resolve, 300));
          await page.waitFor('JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).mode === "Title"',
            { timeoutMs: 10000, label: 'title before co-op join' });
          const tap = async (key) => {
            await page.key(key, key, key === 'Enter' ? 13 : 40);
            await new Promise((resolve) => setTimeout(resolve, 300));
          };
          const typeChar = async (ch) => {
            // GetCharPressed listens to keypress; synthesize the full triple.
            await page.keyEvent('keydown', ch, `Key${ch}`, ch.charCodeAt(0));
            await page.evaluate(`window.dispatchEvent(new KeyboardEvent('keypress', { key: ${JSON.stringify(ch)}, charCode: ${ch.charCodeAt(0)}, keyCode: ${ch.charCodeAt(0)}, which: ${ch.charCodeAt(0)}, bubbles: true, cancelable: true }))`);
            await new Promise((resolve) => setTimeout(resolve, 70));
            await page.keyEvent('keyup', ch, `Key${ch}`, ch.charCodeAt(0));
            await new Promise((resolve) => setTimeout(resolve, 120));
          };
          await tap('ArrowDown'); await tap('Enter');   // Title -> Co-op menu (row Host)
          await tap('ArrowDown'); await tap('Enter');   // Code row, start editing
          for (const ch of code) await typeChar(ch);
          await tap('Enter');                           // finish editing
          await tap('ArrowDown'); await tap('Enter');   // Join -> consent
          await tap('Enter');                           // accept consent -> connect
          await page.waitFor('JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).mode === "Coop_Lobby"',
            { timeoutMs: 20000, label: 'joiner lobby' });
          await tap('ArrowDown'); await tap('Enter');   // Ready
          await page.waitFor('JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).mode === "Playing"',
            { timeoutMs: 40000, label: 'co-op run started on the joiner' });
          // Both seats must end up GPU-resident regardless of which pack
          // landed last (2026-10-13: adoption used to unload the other seat).
          await page.waitFor('(() => { const a = JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).actors_resident.split(","); return a.includes("rogue") && a.includes("warden"); })()',
            { timeoutMs: 90000, label: 'both seats resident on the joiner' });
          const joinState = await probe(page);
          const joinDefects = consoleDefects(page);
          record('coop-join-partner-sprite', joinDefects.length === 0 && joinState.packs_failed === 0,
            joinDefects.slice(0, 3).map((d) => `${d.type}: ${d.text.slice(0, 160)}`).join(' | ') || `joined ${code}, run started, resident=${joinState.actors_resident}`);
          // Greedy prefetch: every archetype pack should be resident by now.
          await page.waitFor('JSON.parse(UTF8ToString(Module._ar_web_smoke_probe())).packs_resident >= 5',
            { timeoutMs: 30000, label: 'all archetype packs prefetched' });
          const prefetched = await probe(page);
          record('archetype-prefetch', prefetched.packs_resident >= 5 && prefetched.packs_failed === 0,
            `resident=${prefetched.packs_resident} failed=${prefetched.packs_failed}`);
        } finally {
          bot.kill();
        }
      }
    } finally {
      relay.kill();
    }
  }
} catch (error) {
  record('harness', false, String(error).slice(0, 300));
  if (currentPage) {
    try { await currentPage.screenshot(path.join(evidenceDir, 'smoke-failure.png')); } catch {}
  }
} finally {
  const summary = {
    when: new Date().toISOString(),
    browser: browserName,
    dist,
    entryPath,
    results,
    console: currentPage ? currentPage.sessionConsoleLines.slice(-200) : [],
  };
  await mkdir(evidenceDir, { recursive: true });
  await writeFile(path.join(evidenceDir, 'smoke-report.json'), JSON.stringify(summary, null, 2));
  await browser.close();
  server.kill();
}

const failed = results.filter((result) => !result.ok);
console.log(`web-smoke: ${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length === 0 ? 0 : 1);
