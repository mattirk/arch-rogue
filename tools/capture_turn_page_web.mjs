// Deterministic browser captures of the shared manuscript scene. Node >= 22.
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { CdpBrowser } from './web_cdp.mjs';
const port = 8099;
const output = new URL('../build/turn-page-captures/', import.meta.url);
await mkdir(output, { recursive: true });
const server = spawn('python3', ['tools/web_serve.py', '--root', 'build/web/dist', '--port', String(port)], { stdio: 'ignore' });
let browser;
try {
  for (let attempt = 0; attempt < 50; attempt++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/`)).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  const command = process.env.AR_WEB_BROWSER || 'flatpak';
  browser = await CdpBrowser.launch(command, [], { prefixArgs: command === 'flatpak' ? ['run', 'com.google.Chrome'] : [] });
  for (const scene of ['turn_page', 'turn_page_traverse', 'turn_page_fall']) {
    const page = await browser.openPage();
    await page.setViewport(1280, 720);
    await page.navigate(`http://127.0.0.1:${port}/?play=1&archetype=rogue&seed=9707&story_capture=${scene}`);
    await page.waitForConsole(/ARCH_ROGUE_STORY_CAPTURE ready/, { timeoutMs: 60000 });
    // Capture profiles deliberately disable audio; wait for file materialization,
    // since SFX adoption correctly remains queued until an audio device is ready.
    await page.waitFor('document.getElementById("ar-pack-chip").hidden', { timeoutMs: 60000, label: 'pack files materialized' });
    if (page.pageErrors.length) throw new Error(page.pageErrors.join('\n'));
    const shot = await page.send('Page.captureScreenshot', { format: 'png' });
    await writeFile(new URL(`${scene}_web_1280x720.png`, output), Buffer.from(shot.data, 'base64'));
    await writeFile(new URL(`${scene}_web.log`, output), page.consoleLines.map(line => line.text).join('\n'));
    console.log(`Captured ${scene} in Chromium`);
    await browser.send('Target.closeTarget', { targetId: page.targetId });
  }
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
