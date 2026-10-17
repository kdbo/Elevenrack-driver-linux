// SPDX-License-Identifier: MIT
// Original Electron splash markup and CSS; Tauri only supplies its IPC wiring.
(async () => {
  const {invoke} = window.__TAURI__.core;
  const {listen} = window.__TAURI__.event;
  const call = (method, ...args) => invoke('host_call', {method,args});
  const get = id => document.getElementById(id);
  let fraction = .05;
  const progress = (data = {}) => {
    get('gate-view').classList.remove('open');
    get('progress-view').classList.remove('hidden');
    if (data.message) get('status-text').textContent = data.message;
    if (Number.isFinite(data.fraction)) fraction = Math.max(fraction, Math.min(1, data.fraction));
    get('progress-bar').style.width = Math.max(5, fraction * 100) + '%';
  };
  await listen('splashProgress', event => progress(event.payload[0]));
  await listen('splashHideGate', () => { fraction=.05; progress(); });
  await listen('splashShowGate', event => {
    const data = event.payload[0] || {};
    get('progress-view').classList.add('hidden');
    get('gate-view').classList.add('open');
    get('btn-startup-retry').style.display = data.reason === 'firmware' ? 'none' : '';
    get('gate-msg').textContent = data.reason === 'firmware'
      ? `Unverified firmware: ${data.reportedBuild || 'no reply'}. Supported builds: ${(data.expectedBuilds || []).join(' or ')}.`
      : 'Unable to locate Eleven Rack. Make sure Eleven Rack is connected and turned on. Click Try Again to rescan. Click Quit to close.';
  });
  await listen('splashChooseRack', event => {
    const [devices, token] = event.payload;
    const dialog = document.createElement('dialog');
    const title = document.createElement('p'); title.textContent = 'Select Eleven Rack';
    const select = document.createElement('select');
    for (const device of devices) { const option = document.createElement('option'); option.value = device.id; option.textContent = device.label; select.append(option); }
    const done = choice => { dialog.close(); dialog.remove(); call('splashChoice', {token,choice}); };
    const choose = document.createElement('button'); choose.textContent = 'Connect'; choose.onclick = () => done(select.value);
    const cancel = document.createElement('button'); cancel.textContent = 'Cancel'; cancel.onclick = () => done(null);
    dialog.addEventListener('cancel', event => {event.preventDefault(); done(null);});
    dialog.append(title, select, choose, cancel); document.body.append(dialog); dialog.showModal();
  });
  get('btn-startup-retry').onclick = () => { fraction=.05; progress({message:'Retrying...',fraction:.05}); call('splashRetry'); };
  get('btn-startup-quit').onclick = () => call('quitApp');
  get('version-tag').textContent = 'v' + await call('getAppVersion');
  progress({message:'Starting MIDI...',fraction:.05});
  // Paint the lightweight splash before constructing/loading the heavy editor.
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const bar = get('progress-bar');
  await call('splashReady', {barVisible:bar.getBoundingClientRect().width > 0 && bar.getBoundingClientRect().height > 0, width:innerWidth, height:innerHeight});
})().catch(error => { document.getElementById('status-text').textContent = 'Startup failed: ' + error; });
