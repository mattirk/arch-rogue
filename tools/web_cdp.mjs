// Minimal zero-dependency Chrome DevTools Protocol driver for the Arch Rogue
// web harnesses (boot check, smoke, profiling). Requires Node >= 22 for the
// built-in WebSocket client. Launches a Chromium-family browser headless with
// --remote-debugging-port=0 and drives one page target over the flat protocol.

import { spawn } from 'node:child_process';

export class CdpBrowser {
  constructor(process, socket) {
    this.process = process;
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = [];
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(`${message.error.message} (${message.error.code})`));
        else resolve(message.result);
        return;
      }
      for (const listener of this.listeners) listener(message);
    });
  }

  static async launch(command, extraArgs = [], { timeoutMs = 20000, prefixArgs = [] } = {}) {
    const args = [
      ...prefixArgs,
      '--headless=new',
      '--remote-debugging-port=0',
      '--no-first-run',
      '--no-default-browser-check',
      `--user-data-dir=/tmp/ar-cdp-profile-${process.pid}-${Date.now()}`,
      '--enable-unsafe-swiftshader',
      '--autoplay-policy=no-user-gesture-required',
      '--disable-background-timer-throttling',
      '--disable-renderer-backgrounding',
      '--disable-backgrounding-occluded-windows',
      ...extraArgs,
      'about:blank',
    ];
    const child = spawn(command, args, { stdio: ['ignore', 'ignore', 'pipe'] });
    const wsUrl = await new Promise((resolve, reject) => {
      let buffer = '';
      const timer = setTimeout(() => reject(new Error('browser did not expose a DevTools endpoint in time')), timeoutMs);
      child.stderr.on('data', (chunk) => {
        buffer += chunk.toString();
        const match = buffer.match(/DevTools listening on (ws:\/\/\S+)/);
        if (match) {
          clearTimeout(timer);
          resolve(match[1]);
        }
      });
      child.on('exit', (code) => reject(new Error(`browser exited early (${code})`)));
    });
    const socket = new WebSocket(wsUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, { once: true });
      socket.addEventListener('error', () => reject(new Error('DevTools websocket failed')), { once: true });
    });
    return new CdpBrowser(child, socket);
  }

  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.socket.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }

  onEvent(listener) {
    this.listeners.push(listener);
  }

  async openPage() {
    const { targetId } = await this.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await this.send('Target.attachToTarget', { targetId, flatten: true });
    const page = new CdpPage(this, sessionId, targetId);
    await page.send('Page.enable');
    await page.send('Runtime.enable');
    await page.send('Log.enable');
    await page.send('Network.enable');
    // Headless pages are not focused by default; without focus, dispatched
    // input events never reach the document's listeners.
    await page.send('Page.bringToFront');
    await page.send('Emulation.setFocusEmulationEnabled', { enabled: true });
    return page;
  }

  async close() {
    try { await this.send('Browser.close'); } catch { /* already gone */ }
    this.socket.close();
    await new Promise((resolve) => {
      const timer = setTimeout(() => { this.process.kill('SIGKILL'); resolve(); }, 3000);
      this.process.on('exit', () => { clearTimeout(timer); resolve(); });
    });
  }
}

export class CdpPage {
  constructor(browser, sessionId, targetId) {
    this.browser = browser;
    this.sessionId = sessionId;
    this.targetId = targetId;
    this.consoleLines = [];
    this.pageErrors = [];
    this.sessionConsoleLines = [];
    this.sessionPageErrors = [];
    browser.onEvent((message) => {
      if (message.sessionId !== this.sessionId) return;
      if (message.method === 'Runtime.consoleAPICalled') {
        const text = (message.params.args || [])
          .map((argument) => argument.value !== undefined ? String(argument.value) : (argument.description || ''))
          .join(' ');
        const line = { type: message.params.type, text, at: Date.now() };
        this.consoleLines.push(line);
        this.sessionConsoleLines.push(line);
      } else if (message.method === 'Runtime.exceptionThrown') {
        const detail = message.params.exceptionDetails;
        const description = detail.exception?.description || detail.text || 'unknown page error';
        this.pageErrors.push(description);
        this.sessionPageErrors.push(description);
      } else if (message.method === 'Log.entryAdded') {
        const entry = message.params.entry;
        const logLine = { type: entry.level, text: entry.text, source: entry.source, at: Date.now() };
        this.consoleLines.push(logLine);
        this.sessionConsoleLines.push(logLine);
      }
    });
  }

  send(method, params = {}) {
    return this.browser.send(method, params, this.sessionId);
  }

  // Fresh page, fresh console: per-page buffers reset so waits cannot match
  // lines from before the navigation; session buffers keep everything for the
  // whole-run clean-console verdict.
  async navigate(url) {
    this.consoleLines = [];
    this.pageErrors = [];
    await this.send('Page.navigate', { url });
  }

  async setViewport(width, height, deviceScaleFactor = 1) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      width, height, deviceScaleFactor, mobile: false,
    });
  }

  async evaluate(expression) {
    const { result, exceptionDetails } = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true,
    });
    if (exceptionDetails) {
      throw new Error(`evaluate failed: ${exceptionDetails.exception?.description || exceptionDetails.text}`);
    }
    return result.value;
  }

  async waitFor(expression, { timeoutMs = 60000, pollMs = 250, label = expression } = {}) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const value = await this.evaluate(expression);
      if (value) return value;
      if (Date.now() > deadline) throw new Error(`timeout waiting for: ${label}`);
      await new Promise((resolve) => setTimeout(resolve, pollMs));
    }
  }

  async waitForConsole(pattern, { timeoutMs = 60000, pollMs = 200 } = {}) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const hit = this.consoleLines.find((line) => pattern.test(line.text));
      if (hit) return hit;
      if (Date.now() > deadline) throw new Error(`timeout waiting for console ${pattern}`);
      await new Promise((resolve) => setTimeout(resolve, pollMs));
    }
  }

  // Synthetic pointer+mouse dispatch at the topmost element. CDP Input mouse
  // events are avoided deliberately: in headless they leave the page's GLFW
  // keyboard routing dead (a harness-only artifact — real user clicks behave;
  // audio autoplay is force-allowed for headless runs instead of relying on
  // trusted activation).
  async click(x, y) {
    await this.evaluate(`(() => {
      const target = document.elementFromPoint(${x}, ${y}) || document.body;
      const init = { clientX: ${x}, clientY: ${y}, button: 0, bubbles: true, cancelable: true };
      target.dispatchEvent(new PointerEvent('pointerdown', { ...init, pointerId: 1, isPrimary: true }));
      target.dispatchEvent(new MouseEvent('mousedown', init));
      target.dispatchEvent(new PointerEvent('pointerup', { ...init, pointerId: 1, isPrimary: true }));
      target.dispatchEvent(new MouseEvent('mouseup', init));
      target.dispatchEvent(new MouseEvent('click', init));
      return true;
    })()`);
  }

  // Emscripten's GLFW keyboard handler reliably sees synthetic KeyboardEvents
  // dispatched at window, while CDP Input key events reach the DOM but not the
  // game. Keyboard has no user-activation requirement, so synthetic dispatch
  // is the correct tool; keep trusted CDP input for pointer gestures.
  async keyEvent(type, key, code, keyCode = 0) {
    await this.evaluate(`(() => {
      const init = { key: ${JSON.stringify(key)}, code: ${JSON.stringify(code)},
        keyCode: ${keyCode}, which: ${keyCode}, bubbles: true, cancelable: true };
      window.dispatchEvent(new KeyboardEvent(${JSON.stringify(type)}, init));
      return true;
    })()`);
  }

  // Hold the key across several frames: raylib's IsKeyPressed compares per-
  // frame snapshots, so a down+up pair inside one frame interval is invisible.
  async key(key, code, keyCode = 0, holdMs = 70) {
    await this.keyEvent('keydown', key, code, keyCode);
    await new Promise((resolve) => setTimeout(resolve, holdMs));
    await this.keyEvent('keyup', key, code, keyCode);
  }

  async screenshot(path) {
    const { data } = await this.send('Page.captureScreenshot', { format: 'png' });
    const { writeFile } = await import('node:fs/promises');
    await writeFile(path, Buffer.from(data, 'base64'));
  }
}

export function resolveBrowserCommand(explicit) {
  if (explicit) return explicit;
  if (process.env.AR_WEB_BROWSER) return process.env.AR_WEB_BROWSER;
  return 'flatpak';
}

// Chromium-family launch presets. flatpak Chrome needs the run subcommand
// before the chromium flags.
export async function launchPreset(name, extraArgs = []) {
  if (name === 'chrome-flatpak' || name === 'flatpak') {
    return CdpBrowser.launch('flatpak', extraArgs, { prefixArgs: ['run', 'com.google.Chrome'] });
  }
  return CdpBrowser.launch(name, extraArgs);
}
