#!/usr/bin/env python3
"""Native GTK control panel for the Eleven Rack Linux driver."""
import importlib.util
import hashlib
import json
import math
import fcntl
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
import time

# VS Code's Snap environment can point system GTK at incompatible schemas.
for key in ('GSETTINGS_SCHEMA_DIR', 'GTK_PATH', 'GIO_EXTRA_MODULES'):
    if '/snap/code/' in os.environ.get(key, ''):
        os.environ.pop(key, None)
if '/snap/code/' in os.environ.get('XDG_DATA_DIRS', ''):
    os.environ['XDG_DATA_DIRS'] = ':'.join(
        path for path in os.environ['XDG_DATA_DIRS'].split(':') if '/snap/code/' not in path)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / 'eleven-rack-settings.py'
DRIVER_LOGO = ROOT.parent / 'assets' / 'eleven-rack-control-logo-v2.png'
GLib.set_prgname('eleven-rack-control')
GLib.set_application_name('Eleven Rack Control')
spec = importlib.util.spec_from_file_location('settings', BACKEND)
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)
update_spec = importlib.util.spec_from_file_location('updates', ROOT / 'eleven-rack-updates.py')
updates = importlib.util.module_from_spec(update_spec)
update_spec.loader.exec_module(updates)


def control_preferences():
    try:
        value = json.loads(settings.firmware_cache_path().with_name('control.json').read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_channels_state(expander, *_):
    path = settings.firmware_cache_path().with_name('control.json')
    preferences = control_preferences()
    preferences['channels_expanded'] = expander.get_expanded()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.%d.tmp' % os.getpid())
        temporary.write_text(json.dumps(preferences, indent=2) + '\n')
        temporary.replace(path)
    except OSError:
        pass

CSS = b'''
.eleven-rack-panel { font-size: 12px; background: #101010; color: #eee9e3; }
.eleven-rack-panel scrolledwindow, .eleven-rack-panel viewport { background: #101010; }
.eleven-rack-surface { background-color: #101010; background-image: none; }
.eleven-rack-panel .live-status { background: #211b15; border-top: 1px solid #38312a; padding: 8px 16px; }
.eleven-rack-panel label { color: #eee9e3; }
.eleven-rack-panel .eyebrow { color: #ff8a28; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
.eleven-rack-panel .title { font-size: 24px; font-weight: bold; }
.eleven-rack-panel .subtitle { color: #a39c93; font-size: 12px; }
.eleven-rack-panel label.driver-connected { color: #56d681; }
.eleven-rack-panel levelbar trough { background: #101010; border: none; box-shadow: none; padding: 0; }
.eleven-rack-panel levelbar block { border: none; box-shadow: none; }
.eleven-rack-panel levelbar block.empty { background: #101010; }
.eleven-rack-panel levelbar block.filled { background: #56d681; border-color: #56d681; }
.eleven-rack-panel levelbar block.high { background: #56d681; border-color: #56d681; }
.eleven-rack-panel levelbar block.full { background: #56d681; border-color: #56d681; }
.eleven-rack-panel .card { background: #1c1b19; border: 1px solid #38312a; border-radius: 9px; padding: 8px; }
.eleven-rack-panel .section { font-size: 15px; font-weight: bold; }
.eleven-rack-panel .channel { padding: 4px 0; border-bottom: 1px solid #302b26; font-size: 12px; }
.eleven-rack-panel .channel-card { padding: 8px 12px; }
.eleven-rack-panel expander title { color: #eee9e3; font-size: 14px; font-weight: bold; }
.eleven-rack-panel .number { color: #ff8a28; font-family: monospace; font-weight: bold; }
.eleven-rack-panel .badge { background: #342316; color: #ffac65; border: 1px solid #74401d; border-radius: 14px; padding: 5px 8px; }
.eleven-rack-panel button { background: #302b26; color: #f4eee7; border: 1px solid #504238; border-radius: 7px; padding: 5px 9px; box-shadow: none; }
.eleven-rack-panel button:hover { background: #473326; }
.eleven-rack-panel button.accent { background: #f07820; color: #160c04; border-color: #f07820; font-weight: bold; }
.eleven-rack-panel button.accent:hover { background: #ff943b; }
.eleven-rack-panel button:disabled { background: #25221f; color: #77716a; border-color: #38312a; }
.eleven-rack-panel combobox button { background: #121110; background-image: none; color: #eee9e3; }
.eleven-rack-panel combobox cellview, .eleven-rack-panel combobox label, .eleven-rack-panel combobox arrow { color: #eee9e3; }
.eleven-rack-panel combobox, .eleven-rack-panel entry { background-color: #121110; color: #eee9e3; }
.eleven-rack-panel menu, .eleven-rack-panel .menu, .eleven-rack-panel popover, .eleven-rack-panel popover contents { background: #1c1b19; color: #eee9e3; }
.eleven-rack-panel menu menuitem { background: #1c1b19; color: #eee9e3; }
.eleven-rack-panel menu menuitem label, .eleven-rack-panel menu menuitem cellview { color: #eee9e3; }
.eleven-rack-panel menu menuitem:hover { background: #f07820; color: #160c04; }
.eleven-rack-panel menu menuitem:hover label, .eleven-rack-panel menu menuitem:hover cellview { color: #160c04; }
.eleven-rack-panel .notice { background: #211b15; border-left: 3px solid #f07820; padding: 8px; }
.eleven-rack-panel .footer { color: #b5aaa0; font-size: 11px; }
.eleven-rack-panel .clock-dot { color: #706a63; font-size: 19px; padding: 0 8px; }
.eleven-rack-panel .clock-dot.locked { color: #56d681; }
.eleven-rack-panel stack, .eleven-rack-panel notebook, .eleven-rack-panel textview text { background: #101010; color: #eee9e3; }
.eleven-rack-panel button:link, .eleven-rack-panel button:visited { color: #ff8a28; }
window.eleven-rack-about { background-color: #101010; background-image: none; }
.eleven-rack-about-content, .eleven-rack-about-content box,
.eleven-rack-about-content label, .eleven-rack-about-content viewport,
.eleven-rack-about-content scrolledwindow, .eleven-rack-about-content stack,
.eleven-rack-about-content textview, .eleven-rack-about-content textview text {
    background-color: #101010; background-image: none; color: #eee9e3;
}
.eleven-rack-about-content scrolledwindow,
.eleven-rack-about-content frame {
    border: none; box-shadow: none; background-color: #101010; background-image: none;
}
.eleven-rack-about-content scrolledwindow undershoot,
.eleven-rack-about-content scrolledwindow overshoot {
    background-image: none; box-shadow: none;
}
.eleven-rack-about-content label,
.eleven-rack-about-content textview, .eleven-rack-about-content textview text {
    font-family: sans-serif; font-size: 12px;
}
.eleven-rack-about-content label.section { font-size: 15px; font-weight: bold; }
'''


def label(text, style=None):
    widget = Gtk.Label(label=text, xalign=0)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def box(vertical=True, spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                   spacing=spacing)


def about_markup(markup):
    """Remove GTK font overrides while preserving emphasis and clickable links."""
    markup = re.sub(r'</?(?:small|big)\b[^>]*>', '', markup)
    return re.sub(r'(<span\b)([^>]*)(>)',
                  lambda match: match[1] + re.sub(
                      r'\s+(?:size|font|font_desc|font_family|face|scale)\s*=\s*(?:"[^"]*"|\x27[^\x27]*\x27)',
                      '', match[2]) + match[3], markup)


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__(title='Eleven Rack Control')
        self.set_wmclass('eleven-rack-control', 'Eleven Rack Control')
        logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(DRIVER_LOGO), 64, 64, True)
        self.set_icon(logo)
        self.set_default_size(880, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', Gtk.main_quit)
        self.busy = False
        self.device_epoch = 0
        self.selected_device = os.environ.get('ELEVEN_RACK_DEVICE')
        self.device_snapshot = None
        self.polling_lock = False
        self.event_process = None
        self.event_card = None
        self.events_pending = False
        self.connect('destroy', self.stop_control_events)
        self.updating = False
        self.confirmed = {'clock': None, 'rate': None, 'rig-input': None, 'buffer': None, 'monitor': None}
        self.polling_monitor = False
        self.monitor_available = None
        self.monitor_epoch = 0
        self.polling_buffer = False
        self.buttons = []
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.get_style_context().add_class('eleven-rack-surface')
        scroll = Gtk.ScrolledWindow()
        scroll.get_style_context().add_class('eleven-rack-surface')
        layout = box(spacing=0)
        layout.get_style_context().add_class('eleven-rack-panel')
        self.add(layout)
        layout.pack_start(scroll, True, True, 0)
        body = box(spacing=12)
        self.content_body = body
        self.content_resize_pending = False
        self.last_content_height = None
        body.get_style_context().add_class('eleven-rack-panel')
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(body, 'set_margin_' + edge)(16)
        viewport = Gtk.Viewport()
        viewport.set_shadow_type(Gtk.ShadowType.NONE)
        viewport.get_style_context().add_class('eleven-rack-surface')
        viewport.add(body)
        scroll.add(viewport)
        header = box(False, 12)
        self.driver_logo = Gtk.Image.new_from_pixbuf(logo)
        self.driver_logo.set_valign(Gtk.Align.CENTER)
        self.driver_logo.get_accessible().set_name('Eleven Rack Control logo')
        header.pack_start(self.driver_logo, False, False, 0)
        identity = box(spacing=3)
        identity.pack_start(label('ELEVEN RACK  /  LINUX', 'eyebrow'), False, False, 0)
        title_row = box(False, 10)
        title_row.pack_start(label('Eleven Rack Control', 'title'), False, False, 0)
        try:
            version = (ROOT.parent / 'VERSION').read_text().strip()
        except OSError:
            version = 'Development version'
        version_label = label(version, 'subtitle')
        self.installed_version = version
        self.update_result = None
        self.update_check_running = False
        version_label.set_valign(Gtk.Align.CENTER)
        title_row.pack_start(version_label, False, False, 0)
        identity.pack_start(title_row, False, False, 0)
        saved_firmware = settings.cached_firmware_version()
        self.firmware_label = label('Firmware: ' + saved_firmware + ' (saved)' if saved_firmware
                                    else 'Firmware · reading…', 'subtitle')
        identity.pack_start(self.firmware_label, False, False, 0)
        header.pack_start(identity, True, True, 0)
        self.connection = label('Checking driver…', 'subtitle')
        self.connection.set_valign(Gtk.Align.CENTER)
        refresh = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text('Refresh all settings')
        refresh.get_accessible().set_name('Refresh all settings')
        refresh.set_valign(Gtk.Align.CENTER)
        refresh.connect('clicked', lambda _: self.refresh_all())
        self.buttons.append(refresh)
        header.pack_end(refresh, False, False, 0)
        about = Gtk.Button(label='About')
        about.set_valign(Gtk.Align.CENTER)
        about.connect('clicked', self.show_about)
        header.pack_end(about, False, False, 0)
        body.pack_start(header, False, False, 0)
        self.update_button = Gtk.Button(label='Update available')
        self.update_button.set_no_show_all(True)
        self.update_button.connect('clicked', self.show_update_offer)
        body.pack_start(self.update_button, False, False, 0)

        self.device_selector = Gtk.ComboBoxText()
        self.device_selector.connect('changed', self.device_changed)
        self.device_caption = label('Device', 'subtitle')
        self.device_caption.set_no_show_all(True)
        self.device_selector.set_no_show_all(True)
        device_row = box(False, 8)
        self.device_selector.set_hexpand(False)
        self.device_selector.set_halign(Gtk.Align.START)
        self.device_selector.set_size_request(180, -1)
        for cell in self.device_selector.get_cells():
            cell.set_property('ellipsize', Pango.EllipsizeMode.END)
            cell.set_property('max-width-chars', 22)
        device_row.pack_start(self.device_caption, False, False, 0)
        device_row.pack_start(self.device_selector, False, False, 0)
        body.pack_start(device_row, False, False, 0)
        self.buffer_scope = label('Sample rate and buffer size affect the shared PipeWire session.', 'subtitle')
        body.pack_start(self.buffer_scope, False, False, 0)

        control_row = box(False, 12)
        clock_card = self.card('Clock & sample rate')
        self.clock = self.choice(clock_card, 'Clock source', [('internal', 'Internal'), ('aes', 'AES / EBU'), ('spdif', 'S/PDIF')])
        clock_card.remove(self.clock)
        clock_selector = box(False, 6)
        clock_selector.pack_start(self.clock, True, True, 0)
        self.clock_dot = label('●', 'clock-dot')
        clock_selector.pack_start(self.clock_dot, False, False, 0)
        clock_card.pack_start(clock_selector, False, False, 0)
        self.set_clock_lock(None)
        self.rate = self.choice(clock_card, 'Sample rate · shared PipeWire session', [(str(r), f'{r / 1000:g} kHz') for r in settings.RATES])
        self.rate.set_active_id('48000')
        self.buffer = self.choice(clock_card, 'Buffer size',
                                  [(str(n), 'Automatic' if n == 0 else f'{n} samples') for n in settings.BUFFERS])
        self.buffer.set_active(-1)
        self.buffer_options = settings.BUFFERS
        self.buffer_policy = label('', 'subtitle')
        clock_card.pack_start(self.buffer_policy, False, False, 0)
        self.buffer_status = label('Roundtrip latency · reading…', 'subtitle')
        self.clock_status = label('Hardware status has not been read', 'subtitle')
        control_row.pack_start(clock_card, True, True, 0)

        rig_card = self.card('Rig & monitoring')
        names = ('Guitar', 'Re-Amp', 'Microphone', 'Line L', 'Line R', 'Line L + R', 'Digital L', 'Digital R', 'Digital L + R')
        self.rig = self.choice(rig_card, 'Rig Input', list(zip(settings.RIG_INPUTS, names)))
        self.rig.set_active(-1)
        self.rig.set_tooltip_text('Read the current Rig Input, or select one to apply.')
        self.monitor = self.choice(rig_card, 'DAW-only monitoring',
                                   [('hardware', 'Off · Hardware monitoring'), ('daw-only', 'On · DAW only')])
        self.monitor.set_active(-1)
        self.monitor_status = label('Monitoring state unknown', 'subtitle')
        rig_card.pack_start(self.monitor_status, False, False, 0)
        note = label('On: listen through your DAW.\nOff: return monitoring control to the Rack.', 'subtitle')
        note.set_line_wrap(True)
        rig_card.pack_start(note, False, False, 0)
        control_row.pack_start(rig_card, True, True, 0)
        body.pack_start(control_row, False, False, 0)

        self.meter_widgets = []
        self.meter_display_db = [-60.0] * 16
        self.meter_expanders = []
        self.meter_process = None
        self.meter_starting = False
        self.meter_epoch = 0
        self.meter_process_lock = threading.Lock()
        self.meters_suspended = False
        self.connect('destroy', self.stop_meters)
        GLib.timeout_add_seconds(1, self.refresh_meters)
        channels_expander = Gtk.Expander(label='Channels · Inputs & Outputs')
        channels_expander.set_expanded(control_preferences().get('channels_expanded') is True)
        channels_expander.connect('notify::expanded', save_channels_state)
        channels_expander.connect('notify::expanded', self.queue_content_resize)
        channels_expander.connect('notify::expanded', self.refresh_meters)
        self.meter_expanders.append(channels_expander)
        channels = box(False, 12)
        channels.set_margin_top(10)
        for heading, entries in [('Inputs · 8 channels', settings.INPUTS), ('Outputs · 6 channels', settings.OUTPUTS)]:
            card = box(spacing=4)
            card.get_style_context().add_class('card')
            card.get_style_context().add_class('channel-card')
            card.pack_start(label(heading, 'section'), False, False, 0)
            rows = box(spacing=2)
            for number, name in enumerate(entries, 1):
                row = box(False, 14)
                row.get_style_context().add_class('channel')
                row.pack_start(label(f'{number:02}', 'number'), False, False, 0)
                row.pack_start(label(name), True, True, 0)
                meter = Gtk.LevelBar.new_for_interval(0, 1)
                meter.set_size_request(90, 8)
                meter.set_valign(Gtk.Align.CENTER)
                meter.add_offset_value('high', .9)
                meter.add_offset_value('full', 1.0)
                readout = label('—', 'subtitle')
                readout.set_width_chars(8)
                readout.set_xalign(1)
                row.pack_start(meter, False, False, 0)
                row.pack_start(readout, False, False, 0)
                self.meter_widgets.append((meter, readout))
                rows.pack_start(row, False, False, 0)
            if entries == settings.OUTPUTS:
                rig_heading = label('Hardware rig · before output volume', 'subtitle')
                rows.pack_start(rig_heading, False, False, 0)
                for name in ('Rig Output L', 'Rig Output R'):
                    row = box(False, 14)
                    row.pack_start(label(name), True, True, 0)
                    meter = Gtk.LevelBar.new_for_interval(0, 1)
                    meter.set_size_request(90, 8)
                    meter.set_valign(Gtk.Align.CENTER)
                    meter.add_offset_value('high', .9)
                    meter.add_offset_value('full', 1.0)
                    readout = label('—', 'subtitle')
                    readout.set_width_chars(8)
                    readout.set_xalign(1)
                    row.pack_start(meter, False, False, 0)
                    row.pack_start(readout, False, False, 0)
                    self.meter_widgets.append((meter, readout))
                    rows.pack_start(row, False, False, 0)
            card.pack_start(rows, False, False, 0)
            channels.pack_start(card, True, True, 0)
        channels_expander.add(channels)
        body.pack_start(channels_expander, False, False, 0)
        self.message = label('', 'subtitle')
        self.message.set_ellipsize(Pango.EllipsizeMode.END)
        self.message.set_selectable(True)
        self.message.set_no_show_all(True)
        self.message_timer = None
        status = box(False, 20)
        status.get_style_context().add_class('live-status')
        self.status_hardware_rate = '…'
        self.status_stream_rate = '…'
        self.live_sample_rate = label('Sample Rate: … (hardware) / … (ALSA)', 'subtitle')
        self.live_sample_rate.set_tooltip_text('Hardware / active audio stream, in kHz')
        self.live_buffer = label('Buffer · reading…', 'subtitle')
        self.status_values = box(False, 20)
        status.pack_start(self.status_values, True, True, 0)
        status.pack_start(self.message, True, True, 0)
        for field in (self.live_sample_rate, self.live_buffer, self.buffer_status):
            field.set_selectable(True)
            self.status_values.pack_start(field, True, True, 0)
        self.connection.set_xalign(1.0)
        status.pack_end(self.connection, False, False, 0)
        layout.pack_end(status, False, False, 0)
        self.status_bar = status
        self.connect('map', self.queue_content_resize)
        GLib.timeout_add_seconds(1, self.refresh_status_stream)
        self.choices = {'clock': self.clock, 'rate': self.rate, 'rig-input': self.rig, 'buffer': self.buffer, 'monitor': self.monitor}
        for command, choice in self.choices.items():
            choice.connect('changed', self.selection_changed, command)
            choice.set_tooltip_text('Selecting a value applies it immediately.')
        self.refresh_devices()
        self.refresh_connection()
        GLib.timeout_add_seconds(3, self.refresh_connection)
        GLib.timeout_add(2000, self.poll_clock_lock)
        GLib.timeout_add_seconds(2, self.poll_buffer)
        GLib.timeout_add_seconds(5, self.refresh_monitor)
        GLib.idle_add(lambda: (self.poll_buffer(), False)[1])
        # Establish a real rollback value before the first clock selection.
        GLib.idle_add(self.refresh_all)
        GLib.timeout_add_seconds(3, self.check_updates)

    def backend_args(self, command, device_id=None):
        device_id = device_id or self.selected_device
        return [sys.executable, str(BACKEND), '--device', device_id or '__unselected__', *command]

    def device_result(self, epoch, callback, *args):
        if epoch == self.device_epoch:
            return callback(*args)
        return False

    def refresh_devices(self):
        found = settings.rack_devices.devices()
        snapshot = [(d['id'], d['label']) for d in found]
        if snapshot == self.device_snapshot:
            return
        auto_switch = len(found) == 1 and self.selected_device not in [d['id'] for d in found]
        if auto_switch and self.busy:
            return
        self.device_snapshot = snapshot
        self.device_selector.set_visible(len(found) > 1)
        self.device_caption.set_visible(len(found) > 1)
        self.updating = True
        self.device_selector.remove_all()
        self.device_selector.append('__unselected__', 'Select an Eleven Rack…')
        for identity, name in snapshot:
            self.device_selector.append(identity, name)
        old_device = self.selected_device
        if auto_switch:
            self.selected_device = found[0]['id']
        self.device_selector.set_active_id(self.selected_device or '__unselected__')
        if self.device_selector.get_active() < 0:
            self.device_selector.append(self.selected_device, 'Selected Rack disconnected')
            self.device_selector.set_active_id(self.selected_device)
        os.environ['ELEVEN_RACK_DEVICE'] = self.selected_device or '__unselected__'
        self.device_selector.set_tooltip_text(self.device_selector.get_active_text())
        self.updating = False
        if auto_switch and old_device is not None:
            self.device_changed(self.device_selector)

    def device_changed(self, choice):
        if self.updating:
            return
        if self.busy:
            self.updating = True
            choice.set_active_id(self.selected_device or '__unselected__')
            self.updating = False
            return
        self.selected_device = choice.get_active_id()
        choice.set_tooltip_text(choice.get_active_text())
        os.environ['ELEVEN_RACK_DEVICE'] = self.selected_device or '__unselected__'
        self.device_epoch += 1
        self.monitor_epoch += 1
        self.polling_lock = self.polling_monitor = self.polling_buffer = False
        self.stop_control_events()
        self.stop_meters()
        self.confirmed = dict.fromkeys(self.confirmed)
        self.status_hardware_rate = self.status_stream_rate = 'unavailable'
        self.set_clock_lock(None)
        self.firmware_label.set_text('Firmware · reading…')
        self.refresh_all()

    def connect_meter_ports(self, device_id, client_name, process):
        for _ in range(20):
            if process.poll() is not None or device_id != self.selected_device:
                return
            selected = settings.rack_devices.select(device_id)
            objects = json.loads(subprocess.check_output(['pw-dump'], text=True, timeout=3))
            nodes = {o['id']: o.get('info', {}).get('props', {}) for o in objects
                     if o.get('type') == 'PipeWire:Interface:Node'}
            sources, targets = {}, {}
            for obj in objects:
                if obj.get('type') != 'PipeWire:Interface:Port':
                    continue
                props = obj.get('info', {}).get('props', {})
                node = nodes.get(int(props.get('node.id', -1)), {})
                name = props.get('port.name', '')
                if node.get('node.name') == client_name:
                    targets[name] = obj['id']
                if node.get('api.alsa.card.id') == selected['card_id'] and props.get('port.direction') == 'out':
                    sources[name] = obj['id']
            names = list(settings.INPUTS) + ['monitor_' + name for name in settings.OUTPUTS]
            if len(targets) >= 14:
                for index, name in enumerate(names):
                    if name in sources:
                        subprocess.run(['pw-link', str(sources[name]), str(targets['meter_%d' % index])],
                                       capture_output=True, timeout=3, check=True)
                return
            time.sleep(.1)

    def check_updates(self, _button=None, manual=False):
        if self.update_check_running:
            return False
        self.update_check_running = True
        device_id = self.selected_device
        device_epoch = self.device_epoch
        def worker():
            result = updates.check_updates(self.installed_version, 'driver', force=manual)
            GLib.idle_add(self.updates_checked, result, manual)
        threading.Thread(target=worker, daemon=True).start()
        return False

    def updates_checked(self, result, manual):
        self.update_check_running = False
        self.update_result = result
        if result['status'] == 'available':
            self.update_button.set_label('Driver update available: %s — Download and install…' % result['version'])
            self.update_button.show()
            if manual:
                self.show_update_offer()
        elif manual:
            if result['status'] == 'current':
                self.update_button.hide()
            dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                                       buttons=Gtk.ButtonsType.CLOSE,
                                       message_type=Gtk.MessageType.INFO,
                                       text='Update check')
            dialog.format_secondary_text(result.get('message', 'No newer driver package is available for this system.'))
            dialog.connect('response', lambda widget, _response: widget.destroy())
            dialog.show()
        return False

    def show_update_offer(self, _button=None):
        result = self.update_result
        if not result or result['status'] != 'available':
            return
        dialog = Gtk.Dialog(title='Install driver update', transient_for=self, modal=True)
        dialog.add_button('Later', Gtk.ResponseType.CANCEL)
        dialog.add_button('Open download page', Gtk.ResponseType.ACCEPT)
        content = dialog.get_content_area()
        content.set_border_width(16)
        content.set_spacing(12)
        for text in ('Eleven Rack driver %s is available (installed: %s).' % (result['version'], self.installed_version),
                     result['message'], result['package'], result['command']):
            item = label(text)
            item.set_line_wrap(True)
            item.set_max_width_chars(70)
            item.set_selectable(True)
            content.pack_start(item, False, False, 0)
        def response(widget, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                Gtk.show_uri_on_window(self, result['url'], Gdk.CURRENT_TIME)
            widget.destroy()
        dialog.connect('response', response)
        dialog.show_all()

    def stop_meters(self, *_):
        self.meter_epoch += 1
        with self.meter_process_lock:
            process = self.meter_process
            self.meter_process = None
            if process is not None and process.poll() is None:
                process.terminate()

    def refresh_meters(self, *_):
        regression = False
        lock_path = Path('/tmp/eleven-rack-regression-%d.lock' % os.getuid())
        if lock_path.exists():
            try:
                with lock_path.open('r') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                regression = True
            except OSError:
                pass
        # Keep the duplex client alive for live backend latency even when the
        # channel meters are hidden. Only their rendering follows the expander.
        if regression or self.busy or self.meters_suspended:
            self.stop_meters()
            self.meter_display_db = [-60.0] * 16
            for meter, readout in self.meter_widgets:
                meter.set_value(0)
                readout.set_text('paused' if regression else '—')
            return True
        if self.meter_process is not None and self.meter_process.poll() is None or self.meter_starting:
            return True
        self.meter_starting = True
        epoch = self.meter_epoch
        device_id = self.selected_device
        device_epoch = self.device_epoch
        def worker():
            process = None
            try:
                source = ROOT / 'eleven-rack-meters.c'
                cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'eleven-rack'
                cache.mkdir(parents=True, exist_ok=True)
                binary = cache / ('meters-' + hashlib.sha256(source.read_bytes()).hexdigest()[:16])
                if not binary.exists():
                    # Fedora keeps PipeWire's JACK library outside the linker's
                    # default search directories; pw-jack handles runtime lookup.
                    libraries = [Path('/usr/lib64/pipewire-0.3/jack/libjack.so.0'),
                                 Path('/usr/lib/pipewire-0.3/jack/libjack.so.0')]
                    libraries += sorted(Path('/usr/lib').glob('*-linux-gnu/pipewire-0.3/jack/libjack.so.0'))
                    jack_library = next((str(p) for p in libraries if p.is_file()), '-l:libjack.so.0')
                    subprocess.run(['cc', '-std=c11', '-D_DEFAULT_SOURCE', '-O2', str(source), '-o', str(binary), jack_library, '-lm'], check=True, capture_output=True, timeout=30)
                if not device_id or device_id == '__unselected__':
                    return
                settings.rack_devices.select(device_id)
                client_name = 'eleven-control-meters-%d-%d-%s' % (os.getpid(), epoch, hashlib.sha256(device_id.encode()).hexdigest()[:8])
                self.meter_client_name = client_name
                env = os.environ.copy()
                for key in ('PIPEWIRE_QUANTUM', 'PIPEWIRE_LATENCY', 'PIPEWIRE_RATE', 'PIPEWIRE_NODE'):
                    env.pop(key, None)
                with self.meter_process_lock:
                    if epoch != self.meter_epoch or self.busy or self.meters_suspended:
                        return
                    process = subprocess.Popen(['pw-jack', str(binary), '--external', client_name], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
                    self.meter_process = process
                self.connect_meter_ports(device_id, client_name, process)
                for line in process.stdout:
                    values = [float(v) for v in line.split()]
                    if len(values) == 14:
                        GLib.idle_add(self.meters_updated, values, epoch)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                print('Eleven Rack meters:', getattr(error, 'stderr', None) or str(error), file=sys.stderr)
                GLib.idle_add(self.meters_updated, [-1] * 14, epoch)
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                    process.wait()
                self.meter_starting = False
        threading.Thread(target=worker, daemon=True).start()
        return True

    def meters_updated(self, values, epoch):
        if epoch != self.meter_epoch:
            return False
        if not any(e.get_expanded() for e in self.meter_expanders):
            return False
        values = values + values[2:4]
        for index, ((meter, readout), peak) in enumerate(zip(self.meter_widgets, values)):
            db = 20 * math.log10(peak) if peak > 0 else -60
            db = max(-60.0, db, self.meter_display_db[index] - 3.0) if peak >= 0 else -60.0
            self.meter_display_db[index] = db
            meter.set_value(max(0, min(1, (db + 60) / 60)))
            readout.set_text('—' if peak < 0 else 'CLIP' if peak >= 1 else '−∞ dB' if db <= -60 else '%.1f dB' % db)
            meter.set_tooltip_text('Digital stream peak (dBFS)' if peak >= 0 else 'Audio port unavailable')
        return False

    def show_status_message(self, text, seconds=3):
        if self.message_timer is not None:
            GLib.source_remove(self.message_timer)
            self.message_timer = None
        self.message.set_text(text.replace('\n', ' · '))
        self.message.set_tooltip_text(text)
        self.status_values.hide()
        self.message.show()
        if seconds:
            self.message_timer = GLib.timeout_add_seconds(seconds, self.clear_status_message)

    def clear_status_message(self):
        self.message_timer = None
        self.message.hide()
        self.status_values.show()
        return False

    def queue_content_resize(self, *_):
        if not self.content_resize_pending:
            self.content_resize_pending = True
            GLib.idle_add(self.resize_to_content)

    def resize_to_content(self):
        self.content_resize_pending = False
        if not self.get_mapped() or self.is_maximized():
            return False
        width, _ = self.get_size()
        _, body_height = self.content_body.get_preferred_height_for_width(width)
        _, status_height = self.status_bar.get_preferred_height_for_width(width)
        height = body_height + status_height
        monitor = self.get_display().get_monitor_at_window(self.get_window())
        if monitor is not None:
            height = min(height, max(200, monitor.get_workarea().height - 80))
        if height != self.last_content_height:
            self.last_content_height = height
            self.resize(width, height)
        return False

    def show_about(self, _button):
        try:
            version = (ROOT.parent / 'VERSION').read_text().strip()
        except OSError:
            version = 'Development version'
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.get_style_context().add_class('eleven-rack-about')
        dialog.get_content_area().get_style_context().add_class('eleven-rack-panel')
        dialog.get_content_area().get_style_context().add_class('eleven-rack-about-content')
        dialog.get_action_area().get_style_context().add_class('eleven-rack-panel')
        dialog.set_program_name('Eleven Rack Control')
        check = Gtk.Button(label='Check for updates')
        check.connect('clicked', lambda button: self.check_updates(button, manual=True))
        # AboutDialog may hide its action area when using a header bar.
        # Keep the update action in the always-visible content instead.
        dialog.get_content_area().pack_end(check, False, False, 8)
        check.show()
        dialog.set_version(version)
        dialog.set_logo(self.get_icon())
        dialog.set_comments('Linux audio routing and hardware settings for the Eleven Rack.')
        dialog.set_copyright('Copyright © 2026 Koen de Boevé')
        dialog.set_authors(['Koen de Boevé — development and Linux integration'])
        dialog.set_website('https://github.com/kdbo/Elevenrack-driver-linux')
        dialog.set_website_label('Project, documentation and full credits')
        dialog.set_license('Original tools and control panel: MIT.\n'
                           'Original kernel patches and patch helper: GPL-2.0-or-later.\n'
                           'Upstream kernel code and dependencies retain their own licenses.\n'
                           'See LICENSING.md in the project for the complete license scope.')
        dialog.set_wrap_license(True)
        dialog.add_credit_section('Driver and protocol references', [
            'Linux kernel and ALSA contributors', 'Ubuntu kernel team',
            'Matt Housley — eleven-rack-driver',
            'Paul Bender — R11 Audio; hardware-monitoring protocol guidance'])
        dialog.add_credit_section('Audio infrastructure', [
            'PipeWire and WirePlumber contributors', 'DKMS contributors'])
        def find_stack(widget):
            if isinstance(widget, Gtk.Stack):
                return widget
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    stack = find_stack(child)
                    if stack is not None:
                        return stack
            return None
        thanks = box(spacing=16)
        thanks.set_border_width(20)
        thanks.pack_start(label('A big thank you to Paul Bender', 'section'), False, False, 0)
        acknowledgement = label(
            'Paul, thank you for all your help, patience and generosity in sharing your '
            'experience with the Eleven Rack. Your guidance on the hardware, latency '
            'and driver testing has been invaluable.\n\n'
            'I consider you a mentor in bringing this driver to life. Your advice '
            'has helped me understand the challenges and keep moving forward.\n\n'
            'Thank you for helping make this possible.\n\n'
            '— Koen')
        acknowledgement.set_line_wrap(True)
        acknowledgement.set_max_width_chars(60)
        acknowledgement.set_selectable(True)
        thanks.pack_start(acknowledgement, False, False, 0)
        stack = find_stack(dialog.get_content_area())
        if stack is not None:
            stack.set_transition_type(Gtk.StackTransitionType.NONE)
            stack.add_titled(thanks, 'thanks-to', 'Thanks to')
            thanks.show_all()
        else:
            dialog.add_credit_section('Thanks to', [acknowledgement.get_text()])
        def uniform_about_fonts(widget):
            # GTK's built-in pages use small/large markup and a monospace
            # license view. Match the custom acknowledgement's typography.
            if isinstance(widget, Gtk.Label):
                if widget.get_use_markup():
                    markup = widget.get_label()
                    if re.search(r'<(?:b|strong)\b|weight\s*=\s*[\x27"]bold[\x27"]', markup):
                        widget.get_style_context().add_class('section')
                    widget.set_markup(about_markup(markup))
                attributes = widget.get_attributes()
                if attributes is not None:
                    attributes = attributes.copy()
                    attributes.filter(lambda attribute, *_: attribute.klass.type in (
                        Pango.AttrType.FAMILY, Pango.AttrType.SIZE,
                        Pango.AttrType.ABSOLUTE_SIZE, Pango.AttrType.SCALE,
                        Pango.AttrType.FONT_DESC))
                    widget.set_attributes(attributes)
            elif isinstance(widget, Gtk.TextView):
                widget.set_monospace(False)
                # AboutDialog applies a local font override to its license
                # view; inherited CSS alone cannot override that provider.
                if not getattr(widget, '_about_font_normalized', False):
                    provider = Gtk.CssProvider()
                    provider.load_from_data(b'textview, textview text { font-family: sans-serif; font-size: 12px; }')
                    widget.get_style_context().add_provider(
                        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
                    widget._about_font_normalized = True
                def reset_tag_font(tag, *_):
                    for property_name in ('family-set', 'size-set', 'scale-set'):
                        tag.set_property(property_name, False)
                widget.get_buffer().get_tag_table().foreach(reset_tag_font, None)
            if isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    uniform_about_fonts(child)
        uniform_about_fonts(dialog.get_content_area())
        if stack is not None:
            # GTK can create Credits and License widgets when first selected.
            stack.connect('notify::visible-child',
                          lambda *_: uniform_about_fonts(dialog.get_content_area()))
        dialog.connect('response', lambda widget, _response: widget.destroy())
        dialog.show()

    def card(self, title):
        card = box(spacing=7)
        card.get_style_context().add_class('card')
        card.pack_start(label(title, 'section'), False, False, 0)
        return card

    def choice(self, parent, title, options):
        parent.pack_start(label(title, 'subtitle'), False, False, 0)
        choice = Gtk.ComboBoxText()
        for key, text in options:
            choice.append(key, text)
        choice.set_active(0)
        parent.pack_start(choice, False, False, 0)
        return choice

    def button(self, parent, title, callback, accent=False):
        button = Gtk.Button(label=title)
        if accent:
            button.get_style_context().add_class('accent')
        button.connect('clicked', callback)
        parent.pack_start(button, False, False, 0)
        self.buttons.append(button)
        return button

    def refresh_connection(self):
        self.refresh_devices()
        self.device_selector.set_sensitive(not self.busy)
        try:
            number = settings.card()
            connected = True
            audio = Path(f'/proc/asound/card{number}/stream0').exists()
            self.connection.set_text('● Driver connected' if audio else 'Driver connected · MIDI only')
            self.connection.get_style_context().add_class('driver-connected')
            if self.event_card != number or self.event_process is None:
                self.poll_monitor()
            self.start_control_events(number)
        except RuntimeError:
            self.stop_meters()
            connected = False
            self.connection.set_text('Driver disconnected')
            self.connection.get_style_context().remove_class('driver-connected')
            self.set_clock_lock(None)
            self.stop_control_events()
            self.monitor_status.set_text('Monitoring state unknown')
            self.confirmed['monitor'] = None
            self.monitor_available = None
            self.monitor_epoch += 1
            self.updating = True
            self.monitor.set_active(-1)
            self.updating = False
        for button in self.buttons:
            button.set_sensitive(connected and not self.busy)
        for choice in self.choices.values():
            choice.set_sensitive(connected and not self.busy)
        self.monitor.set_sensitive(connected and not self.busy and self.monitor_available is not False)
        return True

    def start_control_events(self, number):
        if self.event_process is not None and self.event_process.poll() is None and self.event_card == number:
            return
        self.stop_control_events()
        try:
            self.event_process = subprocess.Popen(
                ['stdbuf', '-oL', 'amixer', '-c', str(number), 'events'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self.event_card = number
            GLib.io_add_watch(self.event_process.stdout, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
                              self.control_event, self.event_process)
        except OSError:
            self.event_process = None

    def stop_control_events(self, *_):
        if self.event_process is not None:
            process = self.event_process
            self.event_process = None
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()
        self.event_card = None

    def control_event(self, stream, condition, process):
        if process is not self.event_process:
            return False
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            self.stop_control_events()
            self.set_clock_lock(None)
            return False
        line = stream.readline()
        if not line:
            return False
        if b'Clock' in line or b'clock' in line:
            if self.busy:
                self.events_pending = True
            else:
                self.poll_clock_lock()
        if b'Monitoring Mode' in line:
            self.poll_monitor()
        return True

    def poll_monitor(self):
        if self.polling_monitor or self.busy:
            return
        self.polling_monitor = True
        epoch = self.monitor_epoch
        device_id = self.selected_device
        device_epoch = self.device_epoch
        def worker():
            try:
                result = subprocess.run(self.backend_args(['monitor'], device_id),
                                        capture_output=True, text=True, timeout=6)
                text = result.stdout if result.returncode == 0 else ''
            except (OSError, subprocess.TimeoutExpired):
                text = ''
            GLib.idle_add(self.device_result, device_epoch, self.monitor_polled, text, epoch)
        threading.Thread(target=worker, daemon=True).start()

    def refresh_monitor(self):
        if self.connection.get_text() != 'Disconnected':
            self.poll_monitor()
        return True

    def monitor_polled(self, text, epoch):
        self.polling_monitor = False
        if epoch != self.monitor_epoch:
            return False
        if not self.busy:
            match = re.search(r'^Monitoring mode: (hardware|daw-only|software-mix|unknown)$', text, re.MULTILINE)
            value = match[1] if match else None
            self.monitor_available = bool(match)
            self.updating = True
            try:
                self.confirmed['monitor'] = value if value in ('hardware', 'daw-only') else None
                self.monitor.set_active_id(value) if self.confirmed['monitor'] else self.monitor.set_active(-1)
                names = {'hardware': 'Hardware monitoring', 'daw-only': 'DAW only',
                         'software-mix': 'Custom software monitoring', 'unknown': 'Monitoring state unknown'}
                self.monitor_status.set_text(names.get(value, 'Monitoring status unavailable'))
                self.monitor.set_sensitive(bool(match))
            finally:
                self.updating = False
        return False

    def set_clock_lock(self, locked):
        style = self.clock_dot.get_style_context()
        if locked is True:
            style.add_class('locked')
            description = 'Clock locked'
        else:
            style.remove_class('locked')
            description = 'Clock unlocked' if locked is False else 'Clock lock unknown'
        self.clock_dot.set_tooltip_text(description)
        self.clock_dot.get_accessible().set_name(description)

    def refresh_all(self):
        if self.busy:
            return False
        self.busy = True
        self.monitor_epoch += 1
        self.refresh_connection()
        self.show_status_message('Refreshing settings…', 0)
        device_id = self.selected_device
        device_epoch = self.device_epoch
        def worker():
            results = {}
            for command in ('status', 'monitor', 'buffer', 'rig-input', 'firmware'):
                try:
                    result = subprocess.run(self.backend_args([command], device_id),
                                            capture_output=True, text=True, timeout=8)
                    results[command] = (result.stdout.strip() if result.returncode == 0
                                        else result.stderr.strip(), result.returncode == 0)
                except (OSError, subprocess.TimeoutExpired) as error:
                    results[command] = (str(error), False)
            GLib.idle_add(self.device_result, device_epoch, self.all_refreshed, results)
        threading.Thread(target=worker, daemon=True).start()
        return False

    def all_refreshed(self, results):
        self.busy = False
        firmware, firmware_ok = results['firmware']
        self.firmware_label.set_text(firmware if firmware_ok else 'Firmware · unavailable')
        self.firmware_label.set_tooltip_text(firmware)
        status, status_ok = results['status']
        self.lock_polled(status if status_ok else '')
        self.clock_status.set_text(status.splitlines()[-1] if status_ok and status else 'Clock status unavailable')
        monitor, monitor_ok = results['monitor']
        self.monitor_polled(monitor if monitor_ok else '', self.monitor_epoch)
        buffer, buffer_ok = results['buffer']
        self.buffer_polled(buffer if buffer_ok else '')
        rig, rig_ok = results['rig-input']
        match = re.search(r'^Rig Input: (\S+)$', rig, re.MULTILINE) if rig_ok else None
        self.updating = True
        try:
            value = match[1] if match and match[1] in settings.RIG_INPUTS else None
            self.confirmed['rig-input'] = value
            self.rig.set_active_id(value) if value else self.rig.set_active(-1)
        finally:
            self.updating = False
        self.refresh_connection()
        errors = [command + ': ' + text for command, (text, ok) in results.items() if not ok and command != 'firmware']
        self.show_status_message('Settings refreshed.' if not errors else 'Refresh incomplete: ' + '\n'.join(errors), 0 if errors else 3)
        return False

    def update_clock_lock(self, text):
        for line in text.splitlines():
            if line.startswith('Clock locked: '):
                self.set_clock_lock(line.split(': ', 1)[1].startswith('True'))
                return
        self.set_clock_lock(None)

    def poll_clock_lock(self):
        if self.busy or self.polling_lock:
            return True
        self.polling_lock = True
        device_id = self.selected_device
        device_epoch = self.device_epoch
        def worker():
            try:
                result = subprocess.run(self.backend_args(['status'], device_id),
                                        capture_output=True, text=True, timeout=8)
                text = result.stdout if result.returncode == 0 else ''
            except (OSError, subprocess.TimeoutExpired):
                text = ''
            GLib.idle_add(self.device_result, device_epoch, self.lock_polled, text)
        threading.Thread(target=worker, daemon=True).start()
        return True

    def update_status_sample_rate(self):
        self.live_sample_rate.set_text('Sample Rate: %s (hardware) / %s (ALSA)' % (self.status_hardware_rate, self.status_stream_rate))

    def refresh_status_stream(self):
        try:
            rates = set()
            for params in Path('/proc/asound/card%d' % settings.card()).glob('pcm*/sub*/hw_params'):
                match = re.search(r'^rate:\s+(\d+)', params.read_text(), re.MULTILINE)
                if match:
                    rates.add(int(match[1]))
            text = ('%.3g kHz' % (next(iter(rates)) / 1000)) if len(rates) == 1 else ('idle' if not rates else 'changing')
        except (RuntimeError, OSError):
            text = 'unavailable'
        self.status_stream_rate = text
        self.update_status_sample_rate()
        return True

    def lock_polled(self, text):
        self.polling_lock = False
        if not self.busy:
            self.update_clock_lock(text)
            self.updating = True
            try:
                match = re.search(r'Hardware sample rate: (\d+) Hz', text)
                if match:
                    value = match.group(1)
                    self.status_hardware_rate = '%g kHz' % (int(value) / 1000)
                    self.update_status_sample_rate()
                    self.confirmed['rate'] = value
                    self.rate.set_active_id(value)
                    self.update_buffer_options()
                else:
                    self.status_hardware_rate = 'unavailable'
                    self.update_status_sample_rate()
                for line in text.splitlines():
                    if line.startswith('Clock: '):
                        value = line.split(': ', 1)[1]
                        if value in settings.CLOCKS:
                            self.confirmed['clock'] = value
                            self.clock.set_active_id(value)
            finally:
                self.updating = False
        return False

    def update_buffer_options(self):
        rate = int(self.confirmed['rate'] or 0)
        options = settings.available_buffers(rate)
        updating = self.updating
        self.updating = True
        try:
            if options != self.buffer_options:
                self.buffer.remove_all()
                for n in options:
                    self.buffer.append(str(n), 'Automatic' if n == 0 else f'{n} samples')
                self.buffer_options = options
            value = self.confirmed['buffer']
            if value is not None and int(value) in options:
                self.buffer.set_active_id(value)
            else:
                self.buffer.set_active(-1)
            note = ''
            if value is not None and int(value) not in options:
                note = 'Current buffer is unsupported; select an available size.'
            self.buffer_policy.set_text(note)
        finally:
            self.updating = updating

    def selection_changed(self, choice, command):
        value = choice.get_active_id()
        if not self.updating and value is not None:
            self.run([command, value])

    def poll_buffer(self):
        if self.busy or self.polling_buffer:
            return True
        self.polling_buffer = True
        device_id = self.selected_device
        device_epoch = self.device_epoch
        def worker():
            try:
                result = subprocess.run(self.backend_args(['buffer'], device_id),
                                        capture_output=True, text=True, timeout=6)
                text = result.stdout if result.returncode == 0 else ''
            except (OSError, subprocess.TimeoutExpired):
                text = ''
            GLib.idle_add(self.device_result, device_epoch, self.buffer_polled, text)
        threading.Thread(target=worker, daemon=True).start()
        return True

    def buffer_polled(self, text):
        self.polling_buffer = False
        if not self.busy:
            self.updating = True
            try:
                for line in text.splitlines():
                    if line.startswith('Buffer size: '):
                        value = line.split(': ', 1)[1]
                        self.live_buffer.set_text('Buffer · ' + ('automatic' if value == '0' else value + ' samples'))
                        self.confirmed['buffer'] = value
                        self.buffer.set_active_id(value)
                    elif line.startswith('Current buffer: '):
                        self.live_buffer.set_text('Buffer · %s (Automatic)' % line.split(': ', 1)[1])
                    elif line.startswith('Roundtrip latency: '):
                        self.buffer_status.set_text(line.split(': ', 1)[1])
                        self.buffer_status.set_tooltip_text('Current roundtrip latency reported by the audio backend, including configured corrections. No loopback measurement is performed.')
                self.update_buffer_options()
                if not text:
                    self.buffer_status.set_text('PipeWire buffer status unavailable')
                    self.live_buffer.set_text('Buffer · unavailable')
            finally:
                self.updating = False
        return False

    def run(self, command):
        if self.busy or any(part is None for part in command):
            return
        self.busy = True
        meter_to_stop = self.meter_process if command[0] in ('clock', 'rate') else None
        if command[0] in ('clock', 'rate'):
            self.meters_suspended = True
            self.stop_meters()
        if command[0] == 'monitor':
            self.monitor_epoch += 1
        if command[0] == 'clock':
            self.set_clock_lock(None)
        self.refresh_connection()
        self.show_status_message('Reading hardware…' if len(command) == 1 else 'Applying setting…', 0)
        device_id = self.selected_device
        device_epoch = self.device_epoch
        def worker():
            try:
                if command[0] in ('clock', 'rate'):
                    if meter_to_stop is not None:
                        meter_to_stop.wait(timeout=3)
                    waiting = time.monotonic() + 5
                    while self.meter_starting and time.monotonic() < waiting:
                        time.sleep(.05)
                    if self.meter_starting:
                        raise RuntimeError('Meters are still stopping; retry the setting change.')
                    # Let PipeWire suspend after our meter client disconnects.
                    # Other audio clients still cause the backend idle check to reject.
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        stream = Path('/proc/asound/card%d/stream0' % settings.rack_devices.select(device_id)['card'])
                        if not stream.exists() or 'Status: Running' not in stream.read_text():
                            break
                        time.sleep(.1)
                invocation = self.backend_args(command, device_id)
                result = subprocess.run(invocation, capture_output=True, text=True, timeout=120)
                text = result.stdout.strip() if result.returncode == 0 else result.stderr.strip() or 'Authentication cancelled or setting not applied.'
                success = result.returncode == 0
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                text, success = str(error), False
            GLib.idle_add(self.device_result, device_epoch, self.finished, command, text, success)
        threading.Thread(target=worker, daemon=True).start()

    def finished(self, command, text, success):
        self.busy = False
        self.show_status_message('Buffer setting applied.' if success and command[0] == 'buffer' and len(command) > 1 else text, 3 if success else 0)
        if command[0] in ('status', 'clock'):
            self.update_clock_lock(text if success else '')
        self.updating = True
        try:
            if success:
                for line in text.splitlines():
                    key, value = None, None
                    if line.startswith('Rig Input: '):
                        key, value = 'rig-input', line.split(': ', 1)[1]
                    elif line.startswith('Clock: '):
                        key, value = 'clock', line.split(': ', 1)[1]
                    elif line.startswith('Internal clock rate: '):
                        key, value = 'rate', line.split()[3]
                    elif line.startswith('Buffer size: '):
                        key, value = 'buffer', line.split(': ', 1)[1]
                    elif line.startswith('Monitoring mode: '):
                        key, value = 'monitor', line.split(': ', 1)[1]
                    elif line.startswith('Roundtrip latency: '):
                        self.buffer_status.set_text(line.split(': ', 1)[1])
                        self.buffer_status.set_tooltip_text('Current roundtrip latency reported by the audio backend, including configured corrections. No loopback measurement is performed.')
                    if key is not None:
                        self.confirmed[key] = value
                        self.choices[key].set_active_id(value)
                if command[0] in ('status', 'clock', 'rate') and text:
                    self.clock_status.set_text(text.splitlines()[-1])
            elif len(command) > 1:
                choice = self.choices[command[0]]
                value = self.confirmed[command[0]]
                if value is None:
                    choice.set_active(-1)
                else:
                    choice.set_active_id(value)
        finally:
            self.updating = False
        self.update_buffer_options()
        self.refresh_connection()
        if command[0] == 'monitor':
            self.poll_monitor()
        self.meters_suspended = False
        if len(command) > 1 or self.events_pending:
            self.events_pending = False
            self.poll_clock_lock()
        return False


if __name__ == '__main__':
    window = Panel()
    window.show_all()
    Gtk.main()
