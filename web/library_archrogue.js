// Arch Rogue Emscripten JS library: IndexedDB persistence bridge, clock/query
// helpers, and shell hooks. Merged into the runtime via --js-library; every
// ar_js_* symbol here backs a foreign import in src/main_web.odin.
//
// Persistence model: the wasm side mirrors documents in memory and calls put/
// delete here on every mutation. Writes are asynchronous IndexedDB requests —
// no Wasm threads, no cross-origin isolation, and deliberately no claim of
// synchronous durability. A write that fails is surfaced on the console and
// counted; the wasm mirror remains the session's source of truth.

addToLibrary({
  $ARWeb: {
    db: null,
    dbFailed: false,
    pendingWrites: 0,
    writeErrors: 0,
    openWaiters: [],
    packMaterializeQueue: [],
    packMaterializeFramePending: false,
    packMaterializeStopped: false,

    schedulePackMaterialization: function () {
      if (ARWeb.packMaterializeStopped || ARWeb.packMaterializeFramePending ||
          ARWeb.packMaterializeQueue.length === 0) return;
      ARWeb.packMaterializeFramePending = true;
      requestAnimationFrame(function () {
        ARWeb.packMaterializeFramePending = false;
        if (ARWeb.packMaterializeStopped) return;
        ARWeb.materializeNextPackFile();
      });
    },

    enqueuePackMaterialization: function (job) {
      if (ARWeb.packMaterializeStopped) return;
      ARWeb.packMaterializeQueue.push(job);
      ARWeb.shellHook('packProgress', {
        name: job.name, state: 'materializing', loaded: 0, total: job.index.length,
      });
      ARWeb.schedulePackMaterialization();
    },

    // One global queue caps MEMFS work at one packed file per browser frame,
    // regardless of how many concurrent fetches finish together.
    materializeNextPackFile: function () {
      if (ARWeb.packMaterializeStopped || ARWeb.packMaterializeQueue.length === 0) return;
      var job = ARWeb.packMaterializeQueue[0];
      if (job.nextEntry >= job.index.length) {
        ARWeb.packMaterializeQueue.shift();
        Promise.resolve().then(job.complete).catch(function () {});
        ARWeb.schedulePackMaterialization();
        return;
      }

      var entry = job.index[job.nextEntry];
      try {
        FS.mkdirTree(entry.path.substring(0, entry.path.lastIndexOf('/')));
        FS.writeFile(entry.path, job.bytes.subarray(
          job.base + entry.offset,
          job.base + entry.offset + entry.size,
        ));
      } catch (error) {
        ARWeb.packMaterializeQueue.shift();
        Promise.resolve().then(job.fail).catch(function () {});
        ARWeb.schedulePackMaterialization();
        return;
      }

      job.nextEntry += 1;
      ARWeb.shellHook('packProgress', {
        name: job.name,
        state: 'materializing',
        loaded: job.nextEntry,
        total: job.index.length,
      });
      if (job.nextEntry >= job.index.length) {
        ARWeb.packMaterializeQueue.shift();
        Promise.resolve().then(job.complete).catch(function () {});
      }
      ARWeb.schedulePackMaterialization();
    },

    open: function (callback) {
      if (ARWeb.db || ARWeb.dbFailed) {
        callback(ARWeb.db);
        return;
      }
      ARWeb.openWaiters.push(callback);
      if (ARWeb.openWaiters.length > 1) return;
      var finish = function (db) {
        ARWeb.db = db;
        ARWeb.dbFailed = !db;
        var waiters = ARWeb.openWaiters;
        ARWeb.openWaiters = [];
        for (var i = 0; i < waiters.length; i++) waiters[i](db);
      };
      var request;
      try {
        request = indexedDB.open('arch-rogue-save', 1);
      } catch (error) {
        finish(null);
        return;
      }
      request.onupgradeneeded = function (event) {
        var db = event.target.result;
        if (!db.objectStoreNames.contains('kv')) {
          db.createObjectStore('kv');
        }
      };
      request.onsuccess = function (event) { finish(event.target.result); };
      request.onerror = function () { finish(null); };
      request.onblocked = function () { finish(null); };
    },

    keyFromHeap: function (ptr, len) {
      return UTF8ToString(ptr, len);
    },

    shellHook: function (name, argument) {
      var shell = Module['arShell'];
      if (shell && typeof shell[name] === 'function') {
        try { shell[name](argument); } catch (error) { /* shell hooks must not break the runtime */ }
      }
    },
  },

  ar_js_console_log__deps: ['$ARWeb'],
  ar_js_console_log: function (level, ptr, length) {
    var message = UTF8ToString(ptr, length);
    if (level >= 3) console.error(message);
    else if (level === 2) console.warn(message);
    else console.log(message);
    // Profiling harness channel: machine-readable perf lines POST to a
    // same-origin endpoint so Firefox (no CDP) can be measured identically.
    if (Module['arReportEndpoint'] && /^MX[A-Z0-9_]*_PERF /.test(message)) {
      try {
        fetch(Module['arReportEndpoint'], { method: 'POST', body: message, keepalive: true }).catch(function () {});
      } catch (error) { /* report channel is best-effort */ }
    }
  },

  ar_js_utc_rfc3339: function (buffer, capacity) {
    var stamp = new Date().toISOString();
    if (stamp.length + 1 > capacity) return 0;
    stringToUTF8(stamp, buffer, capacity);
    return stamp.length;
  },

  ar_js_unix_ms: function () {
    return Date.now();
  },

  ar_js_canvas_width: function () {
    return Module['canvas'] ? Module['canvas'].width : 0;
  },

  ar_js_canvas_height: function () {
    return Module['canvas'] ? Module['canvas'].height : 0;
  },

  ar_js_query_param: function (namePtr, nameLen, buffer, capacity) {
    var name = UTF8ToString(namePtr, nameLen);
    var value = null;
    try {
      value = new URLSearchParams(location.search).get(name);
    } catch (error) {
      value = null;
    }
    if (value === null || value === '') return 0;
    var bytes = lengthBytesUTF8(value);
    if (bytes + 1 > capacity) return 0;
    stringToUTF8(value, buffer, capacity);
    return bytes;
  },

  ar_js_request_fullscreen: function (enable) {
    try {
      if (enable) {
        var canvas = Module['canvas'];
        if (canvas && canvas.requestFullscreen && !document.fullscreenElement) {
          canvas.requestFullscreen().catch(function () {});
        }
      } else if (document.fullscreenElement && document.exitFullscreen) {
        document.exitFullscreen().catch(function () {});
      }
    } catch (error) { /* fullscreen is best-effort; user gesture rules apply */ }
  },

  ar_js_storage_hydrate__deps: ['$ARWeb', 'malloc', 'free'],
  ar_js_storage_hydrate: function () {
    var done = function () { Module['_ar_web_store_hydrate_done'](); };
    ARWeb.open(function (db) {
      if (!db) {
        console.warn('arch-rogue: IndexedDB unavailable; saves last only for this session');
        done();
        return;
      }
      var transaction, cursorRequest;
      try {
        transaction = db.transaction('kv', 'readonly');
        cursorRequest = transaction.objectStore('kv').openCursor();
      } catch (error) {
        done();
        return;
      }
      cursorRequest.onsuccess = function (event) {
        var cursor = event.target.result;
        if (!cursor) {
          done();
          return;
        }
        var key = String(cursor.key);
        var value = cursor.value instanceof Uint8Array ? cursor.value : new Uint8Array(cursor.value);
        var keyBytes = lengthBytesUTF8(key);
        var keyPtr = _malloc(keyBytes + 1);
        stringToUTF8(key, keyPtr, keyBytes + 1);
        var dataPtr = _malloc(value.length > 0 ? value.length : 1);
        if (value.length > 0) HEAPU8.set(value, dataPtr);
        Module['_ar_web_store_hydrate_entry'](keyPtr, keyBytes, dataPtr, value.length);
        _free(keyPtr);
        _free(dataPtr);
        cursor.continue();
      };
      cursorRequest.onerror = function () { done(); };
    });
  },

  ar_js_storage_put__deps: ['$ARWeb'],
  ar_js_storage_put: function (keyPtr, keyLen, dataPtr, dataLen) {
    var key = ARWeb.keyFromHeap(keyPtr, keyLen);
    var bytes = new Uint8Array(dataLen);
    if (dataLen > 0) bytes.set(HEAPU8.subarray(dataPtr, dataPtr + dataLen));
    ARWeb.pendingWrites += 1;
    ARWeb.open(function (db) {
      if (!db) { ARWeb.pendingWrites -= 1; return; }
      try {
        var transaction = db.transaction('kv', 'readwrite');
        transaction.objectStore('kv').put(bytes, key);
        transaction.oncomplete = function () { ARWeb.pendingWrites -= 1; };
        transaction.onabort = transaction.onerror = function () {
          ARWeb.pendingWrites -= 1;
          ARWeb.writeErrors += 1;
          console.error('arch-rogue: IndexedDB write failed for ' + key);
        };
      } catch (error) {
        ARWeb.pendingWrites -= 1;
        ARWeb.writeErrors += 1;
        console.error('arch-rogue: IndexedDB write failed for ' + key);
      }
    });
  },

  ar_js_storage_delete__deps: ['$ARWeb'],
  ar_js_storage_delete: function (keyPtr, keyLen) {
    var key = ARWeb.keyFromHeap(keyPtr, keyLen);
    ARWeb.open(function (db) {
      if (!db) return;
      try {
        db.transaction('kv', 'readwrite').objectStore('kv').delete(key);
      } catch (error) { /* deletes are advisory cleanup */ }
    });
  },

  // Fetch and digest packs concurrently, but materialize their files through
  // ARWeb's single RAF queue. Wasm is notified only after every file for that
  // pack is resident in MEMFS; actor/SFX adoption is queued separately.
  ar_js_pack_request__deps: ['$ARWeb', '$FS', 'malloc', 'free'],
  ar_js_pack_request: function (namePtr, nameLen) {
    var name = UTF8ToString(namePtr, nameLen);
    var settled = false;
    var report = function (ok, actorsCsv, sfxBanksCsv) {
      var nameBytes = lengthBytesUTF8(name);
      var namePointer = _malloc(nameBytes + 1);
      stringToUTF8(name, namePointer, nameBytes + 1);
      var actorBytes = lengthBytesUTF8(actorsCsv);
      var actorPointer = _malloc(actorBytes + 1);
      stringToUTF8(actorsCsv, actorPointer, actorBytes + 1);
      var sfxBytes = lengthBytesUTF8(sfxBanksCsv);
      var sfxPointer = _malloc(sfxBytes + 1);
      stringToUTF8(sfxBanksCsv, sfxPointer, sfxBytes + 1);
      Module['_ar_web_pack_loaded'](
        namePointer, nameBytes, actorPointer, actorBytes, sfxPointer, sfxBytes, ok ? 1 : 0
      );
      _free(namePointer);
      _free(actorPointer);
      _free(sfxPointer);
    };
    var fail = function () {
      if (settled) return;
      settled = true;
      ARWeb.shellHook('packProgress', { name: name, state: 'failed' });
      report(false, '', '');
    };
    var complete = function () {
      if (settled) return;
      settled = true;
      ARWeb.shellHook('packProgress', { name: name, state: 'done' });
      report(true, (info.actors || []).join(','), (info.sfx_banks || []).join(','));
    };
    var manifest = Module['arPacks'];
    var info = manifest && manifest.packs && manifest.packs[name];
    if (!info) {
      Promise.resolve().then(fail).catch(function () {});
      return;
    }
    Promise.resolve().then(function () {
      return fetch(info.url);
    }).then(function (response) {
      if (!response.ok) throw new Error('http ' + response.status);
      var total = info.bytes || Number(response.headers.get('Content-Length')) || 0;
      if (!response.body || !response.body.getReader) return response.arrayBuffer();
      var reader = response.body.getReader();
      var received = 0;
      var chunks = [];
      var pump = function () {
        return reader.read().then(function (step) {
          if (step.done) {
            var whole = new Uint8Array(received);
            var offset = 0;
            chunks.forEach(function (chunk) { whole.set(chunk, offset); offset += chunk.length; });
            return whole.buffer;
          }
          chunks.push(step.value);
          received += step.value.length;
          ARWeb.shellHook('packProgress', { name: name, state: 'fetching', loaded: received, total: total });
          return pump();
        });
      };
      return pump();
    }).then(function (buffer) {
      return crypto.subtle.digest('SHA-256', buffer).then(function (digest) {
        var hex = Array.prototype.map.call(new Uint8Array(digest), function (byte) {
          return byte.toString(16).padStart(2, '0');
        }).join('');
        if (hex !== info.sha256) throw new Error('pack digest mismatch');
        var bytes = new Uint8Array(buffer);
        var magic = 'ARPACK1\n';
        for (var i = 0; i < magic.length; i++) {
          if (bytes[i] !== magic.charCodeAt(i)) throw new Error('bad pack magic');
        }
        var indexLength = new DataView(buffer).getUint32(magic.length, true);
        var indexStart = magic.length + 4;
        var indexEnd = indexStart + indexLength;
        if (indexEnd > bytes.length) throw new Error('pack index exceeds payload');
        var index = JSON.parse(new TextDecoder().decode(bytes.subarray(indexStart, indexEnd)));
        if (!Array.isArray(index)) throw new Error('pack index is not an array');
        ARWeb.enqueuePackMaterialization({
          name: name,
          bytes: bytes,
          index: index,
          base: indexEnd,
          nextEntry: 0,
          complete: complete,
          fail: fail,
        });
      });
    }).catch(fail);
  },

  ar_js_boot_complete__deps: ['$ARWeb'],
  ar_js_boot_complete: function () {
    // Harness hook: lets the smoke tests wait for asynchronous IndexedDB
    // writes to settle before staging reloads or corruption scenarios.
    Module['arStorageStats'] = function () {
      return { pending: ARWeb.pendingWrites, errors: ARWeb.writeErrors };
    };
    ARWeb.shellHook('bootComplete');
  },

  ar_js_boot_failed__deps: ['$ARWeb'],
  ar_js_boot_failed: function (messagePtr, messageLen) {
    ARWeb.shellHook('bootFailed', UTF8ToString(messagePtr, messageLen));
  },

  // ---------------------------------------------------------------------
  // Multiplayer WebSocket bridge (src/net_transport_web.odin). One logical
  // connection at a time; every socket callback is bound to the generation
  // that opened it, so late events from a superseded or closed attempt are
  // ignored. Inbound text is handed to Odin as original UTF-8 bytes: wire
  // numbers are never parsed into JavaScript Numbers here.
  $ARNet: {
    ws: null,
    gen: 0,
    state: 3, // 0 connecting, 1 open, 2 closing, 3 closed, 4 failed
    closeCode: 0,
    error: '',
    queue: [],
    queueBytes: 0,
    maxMessage: 256 * 1024,
    maxQueueBytes: 4 * 1024 * 1024,
    maxQueueCount: 512,
    maxBuffered: 2 * 1024 * 1024,
    encoder: null,

    fail: function (gen, message) {
      if (gen !== ARNet.gen) return;
      ARNet.state = 4;
      if (!ARNet.error) ARNet.error = message;
      try { if (ARNet.ws) ARNet.ws.close(1000); } catch (error) { /* already closing */ }
    },
  },

  ar_js_ws_open__deps: ['$ARNet'],
  ar_js_ws_open: function (urlPtr, urlLen, protoPtr, protoLen) {
    if (ARNet.ws) {
      var old = ARNet.ws;
      old.onopen = old.onmessage = old.onerror = old.onclose = null;
      try { old.close(1000); } catch (error) { /* best effort */ }
    }
    ARNet.gen += 1;
    var gen = ARNet.gen;
    ARNet.ws = null;
    ARNet.state = 0;
    ARNet.closeCode = 0;
    ARNet.error = '';
    ARNet.queue = [];
    ARNet.queueBytes = 0;
    if (!ARNet.encoder) ARNet.encoder = new TextEncoder();
    var url = UTF8ToString(urlPtr, urlLen);
    var protocol = UTF8ToString(protoPtr, protoLen);
    var ws;
    try {
      ws = new WebSocket(url, protocol);
    } catch (error) {
      ARNet.state = 4;
      ARNet.error = String((error && error.message) || error);
      return gen;
    }
    ARNet.ws = ws;
    ws.onopen = function () {
      if (gen !== ARNet.gen) return;
      if (ws.protocol !== protocol) { ARNet.fail(gen, 'server did not accept the protocol'); return; }
      ARNet.state = 1;
    };
    ws.onmessage = function (event) {
      if (gen !== ARNet.gen) return;
      if (typeof event.data !== 'string') { ARNet.fail(gen, 'binary message refused'); return; }
      var bytes = ARNet.encoder.encode(event.data);
      if (bytes.length > ARNet.maxMessage) { ARNet.fail(gen, 'inbound message too large'); return; }
      if (ARNet.queue.length >= ARNet.maxQueueCount || ARNet.queueBytes + bytes.length > ARNet.maxQueueBytes) {
        ARNet.fail(gen, 'inbound queue overflow');
        return;
      }
      ARNet.queue.push(bytes);
      ARNet.queueBytes += bytes.length;
    };
    ws.onerror = function () {
      if (gen !== ARNet.gen) return;
      if (!ARNet.error) ARNet.error = 'connection error';
    };
    ws.onclose = function (event) {
      if (gen !== ARNet.gen) return;
      ARNet.closeCode = event.code;
      ARNet.state = (ARNet.state === 0 || ARNet.state === 4) ? 4 : 3;
      if (ARNet.state === 4 && !ARNet.error) ARNet.error = 'connection closed during handshake';
    };
    return gen;
  },

  ar_js_ws_state__deps: ['$ARNet'],
  ar_js_ws_state: function (gen) {
    return gen === ARNet.gen ? ARNet.state : 3;
  },

  ar_js_ws_close_code__deps: ['$ARNet'],
  ar_js_ws_close_code: function (gen) {
    return gen === ARNet.gen ? ARNet.closeCode : 0;
  },

  ar_js_ws_error__deps: ['$ARNet'],
  ar_js_ws_error: function (gen, buffer, capacity) {
    var text = gen === ARNet.gen ? ARNet.error : '';
    if (!text) return 0;
    var bytes = lengthBytesUTF8(text);
    if (bytes + 1 > capacity) return 0;
    stringToUTF8(text, buffer, capacity);
    return bytes;
  },

  ar_js_ws_send__deps: ['$ARNet'],
  ar_js_ws_send: function (gen, ptr, len) {
    if (gen !== ARNet.gen || ARNet.state !== 1 || !ARNet.ws) return 0;
    // The browser cannot bound its own send queue; refuse rather than grow it.
    if (ARNet.ws.bufferedAmount + len > ARNet.maxBuffered) return 0;
    try {
      ARNet.ws.send(UTF8ToString(ptr, len));
    } catch (error) {
      return 0;
    }
    return 1;
  },

  ar_js_ws_buffered__deps: ['$ARNet'],
  ar_js_ws_buffered: function (gen) {
    return gen === ARNet.gen && ARNet.ws ? ARNet.ws.bufferedAmount : 0;
  },

  ar_js_ws_peek__deps: ['$ARNet'],
  ar_js_ws_peek: function (gen) {
    if (gen !== ARNet.gen || ARNet.queue.length === 0) return -1;
    return ARNet.queue[0].length;
  },

  ar_js_ws_recv__deps: ['$ARNet'],
  ar_js_ws_recv: function (gen, ptr, capacity) {
    if (gen !== ARNet.gen || ARNet.queue.length === 0) return -1;
    var bytes = ARNet.queue[0];
    if (bytes.length > capacity) return -2;
    ARNet.queue.shift();
    ARNet.queueBytes -= bytes.length;
    HEAPU8.set(bytes, ptr);
    return bytes.length;
  },

  // Invalidates the logical connection immediately (no further events reach
  // Odin) and asks the browser to close; queued sends such as bye flush first.
  ar_js_ws_close__deps: ['$ARNet'],
  ar_js_ws_close: function (gen) {
    if (gen !== ARNet.gen) return;
    var ws = ARNet.ws;
    ARNet.gen += 1;
    ARNet.ws = null;
    ARNet.state = 3;
    ARNet.queue = [];
    ARNet.queueBytes = 0;
    if (ws) {
      ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      try { ws.close(1000); } catch (error) { /* best effort */ }
    }
  },

  ar_js_random_bytes: function (ptr, len) {
    crypto.getRandomValues(HEAPU8.subarray(ptr, ptr + len));
  },

  ar_js_game_ended__deps: ['$ARWeb'],
  ar_js_game_ended: function () {
    ARWeb.packMaterializeStopped = true;
    ARWeb.packMaterializeQueue.length = 0;
    ARWeb.shellHook('gameEnded');
  },
});
