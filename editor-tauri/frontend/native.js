// SPDX-License-Identifier: MIT
// Compatibility boundary for the shared editor UI; native services use Tauri IPC.
(function () {
  'use strict';
  const { invoke } = window.__TAURI__.core;
  const { listen } = window.__TAURI__.event;
  const call = (method, ...args) => invoke('host_call', { method, args });
  const subscriptions = new Map();
  function subscribe(name, cb) {
    const pending = listen(name, e => cb(e.payload));
    if (!subscriptions.has(name)) subscriptions.set(name, []);
    subscriptions.get(name).push(pending);
    return () => pending.then(unlisten => unlisten());
  }
  function remove(name) {
    for (const pending of subscriptions.get(name) || []) pending.then(unlisten => unlisten());
    subscriptions.delete(name);
  }
  const api = { platform: 'linux', isElectron: false, isTauri: true, startupTimeoutSec: null };
  const methods = ['getBridgeStatus','restartBridge','quitApp','checkAvidEditor','startWatchdog','stopWatchdog',
    'getSavedMode','saveMode','chooseRack','getSavedPorts','savePorts','getBankCache','saveBankCache',
    'getToneKnobOrder','saveToneKnobOrder','getNumberDisplayMode','saveNumberDisplayMode','getZoom','setZoom',
    'getStartupMode','getAppVersion','checkUpdates','showUpdateOffer','getMidiStackStatus',
    'setWin11UploadWarnDisabled','setWin11StartupAck','logWrite','getLogPath','getLogsEnabled',
    'saveTfx','getCapturesDir','loadTfxDialog','chooseCapturesDir','resetCapturesDir','openPath',
    'openUserManual','getLogsDir','chooseExportDir','exportBank','chooseImportSource','readImportBank'];
  for (const method of methods) api[method] = (...args) => call(method, ...args);
  for (const [method, event] of Object.entries({onBridgeStatus:'bridge-status',onVuLevels:'vu-levels',
    onWatchdogAlert:'watchdog-alert',onSplashProgress:'splash-progress',onSplashShowGate:'splash-show-gate',
    onSplashHideGate:'splash-hide-gate',onStartupRetryClick:'startup-retry-click'})) {
    api[method] = cb => subscribe(event, cb);
  }
  api.removeBridgeStatus = () => remove('bridge-status');
  api.removeWatchdogAlert = () => remove('watchdog-alert');
  function gate(data) {
    let el = document.getElementById('tauri-startup-gate');
    if (!el) {
      el = document.createElement('section'); el.id = 'tauri-startup-gate';
      el.style.cssText = 'position:fixed;inset:0;z-index:99999;background:#111e;display:grid;place-content:center;gap:20px;padding:40px;text-align:center;color:#ddd';
      const title = document.createElement('h2'); title.textContent = 'Eleven Rack Editor';
      const message = document.createElement('p'); message.id = 'tauri-gate-message';
      const retry = document.createElement('button'); retry.textContent = 'Try again';
      retry.onclick = () => { el.hidden = true; el.style.display = 'none'; window.dispatchEvent(new Event('tauri-startup-retry')); };
      const quit = document.createElement('button'); quit.textContent = 'Quit'; quit.onclick = () => api.quitApp();
      el.append(title, message, retry, quit); document.body.append(el);
    }
    el.hidden = false; el.style.display = 'grid';
    document.getElementById('tauri-gate-message').textContent = data && data.reason === 'firmware'
      ? 'The connected Rack firmware is not supported. ' + (data.detail || '')
      : 'Connect your Eleven Rack and try again, or select its MIDI ports.';
  }
  api.splashShowGate = data => gate(data);
  api.splashHideGate = () => { const el = document.getElementById('tauri-startup-gate'); if (el) { el.hidden = true; el.style.display = 'none'; } };
  api.splashProgress = () => {};
  api.appReady = () => { api.splashHideGate(); return call('appReady'); };
  api.onStartupRetryClick = cb => { window.addEventListener('tauri-startup-retry', cb); return () => window.removeEventListener('tauri-startup-retry', cb); };
  api.sendStartupRetryClick = () => window.dispatchEvent(new Event('tauri-startup-retry'));
  api.chooseRack = devices => new Promise(resolve => {
    if (!Array.isArray(devices) || !devices.length || devices.length > 32) { resolve(null); return; }
    const dialog = document.createElement('dialog');
    const label = document.createElement('label'); label.textContent = 'Select Eleven Rack ';
    const select = document.createElement('select');
    for (const device of devices) { const option = document.createElement('option'); option.value = device.id; option.textContent = device.label; select.append(option); }
    label.append(select);
    const choose = document.createElement('button'); choose.textContent = 'Connect';
    const cancel = document.createElement('button'); cancel.textContent = 'Cancel';
    const done = value => { dialog.close(); dialog.remove(); resolve(value); };
    choose.onclick = () => done(select.value); cancel.onclick = () => done(null);
    dialog.addEventListener('cancel', event => { event.preventDefault(); done(null); });
    dialog.append(label, choose, cancel); document.body.append(dialog); dialog.showModal();
  });
  // Retain the shared renderer API name while replacing all Electron IPC.
  window.electronAPI = Object.freeze(api);

  const BrowserWebSocket = window.WebSocket;
  class NativeMidiSocket extends EventTarget {
    constructor(url) {
      super(); this.session = crypto.randomUUID(); this.url = url; this.readyState = 0; this._closed = false; this._queue = Promise.resolve();
      this._subscription = listen('native-midi', event => { if (!this._closed && (!event.payload.session || event.payload.session === this.session)) this._message(event.payload.message); });
      this._subscription.then(() => {
        if (this._closed) return;
        this.readyState = 1; this._fire('open', new Event('open'));
        return invoke('midi_command', { session: this.session, message: { cmd: 'list_ports' } });
      }).then(reply => { if (reply && !this._closed) this._message(reply); }).catch(error => this._error(error));
    }
    _fire(name, event) { this.dispatchEvent(event); const handler = this['on' + name]; if (handler) handler.call(this, event); }
    _message(message) { this._fire('message', new MessageEvent('message', { data: JSON.stringify(message) })); }
    _error(error) { if (!this._closed) this._message({ type:'error', message:String(error) }); }
    send(raw) {
      if (this.readyState !== 1) throw new Error('MIDI connection is not open');
      const message = JSON.parse(raw);
      // Preserve outgoing order across asynchronous Rust IPC calls.
      this._queue = this._queue.then(() => invoke('midi_command', { session: this.session, message }))
        .then(reply => { if (reply && !this._closed) this._message(reply); })
        .catch(error => this._error(error));
    }
    close() {
      if (this._closed) return;
      this._closed = true; this.readyState = 3;
      this._subscription.then(unlisten => unlisten());
      this._queue = this._queue.then(() => invoke('midi_command', { session: this.session, message:{cmd:'disconnect'} })).catch(() => {});
      this._fire('close', new Event('close'));
    }
  }
  class EditorWebSocket extends NativeMidiSocket {
    constructor(url, protocols) {
      if (!/^ws:\/\/(localhost|127\.0\.0\.1):57121\/?$/.test(String(url))) return new BrowserWebSocket(url, protocols);
      super(url);
    }
  }
  for (const [name, value] of Object.entries({CONNECTING:0,OPEN:1,CLOSING:2,CLOSED:3})) EditorWebSocket[name] = value;
  window.WebSocket = EditorWebSocket;
  document.addEventListener('click', event => {
    const link = event.target.closest && event.target.closest('a[href]');
    if (link && /^(https?:|mailto:)/i.test(link.href)) {
      event.preventDefault(); call('openExternal', link.href).catch(console.error);
    }
  });
  async function layoutAudit(interactive) {
    const ids = ['panel-dist','panel-reverb','panel-wah','panel-vol','panel-fxloop','panel-delay','panel-fxhost'];
    const visible = id => getComputedStyle(document.getElementById(id)).display !== 'none';
    const initialHidden = ids.every(id => !visible(id));
    const toneDisplay = getComputedStyle(document.getElementById('tone-knobs-row')).display;
    const checks = [];
    if (interactive) {
      const settle = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      document.querySelector('.chain-open[data-panel="dist"]').click(); await settle();
      checks.push(visible('panel-dist') && !visible('panel-ampcab') && ids.filter(visible).length === 1);
      document.querySelector('.chain-open[data-panel="reverb"]').click(); await settle();
      checks.push(visible('panel-reverb') && !visible('panel-dist') && ids.filter(visible).length === 1);
      document.querySelector('.chain-open[data-panel="reverb"]').click(); await settle();
      checks.push(visible('panel-ampcab') && ids.every(id => !visible(id)));
    }
    const controlLabelFontSize = parseFloat(getComputedStyle(document.querySelector('.amp .ctrl-knob label')).fontSize);
    return { initialHidden, toneDisplay, controlLabelFontSize, panelSwitches:checks, passed:controlLabelFontSize >= 12 && initialHidden && toneDisplay === 'flex' && checks.every(Boolean) };
  }
  document.addEventListener('DOMContentLoaded', () => {
    Promise.all([api.getAppVersion(), api.getCapturesDir(), api.getSavedPorts(), call('getRuntimeInfo')])
      .then(async values => {
        // Exercise panel buttons only in the explicitly MIDI-disabled smoke test.
        const layout = await layoutAudit(values[3].smoke);
        return call('frontendReady', {sharedInit:typeof init === 'function',body:!!document.body,layout});
      })
      .catch(error => call('logWrite', 'JS error: startup verification: ' + String(error)));
  });
  window.addEventListener('error', event => { call('logWrite', 'JS error: ' + event.message).catch(() => {}); });
  window.addEventListener('unhandledrejection', event => { call('logWrite', 'JS rejection: ' + String(event.reason)).catch(() => {}); });
})();
