#!/usr/bin/env python3
"""Native GTK control panel for the Eleven Rack Linux driver."""
import importlib.util
import os
import re
from pathlib import Path
import subprocess
import sys
import threading

# VS Code's Snap environment can point system GTK at incompatible schemas.
for key in ('GSETTINGS_SCHEMA_DIR', 'GTK_PATH', 'GIO_EXTRA_MODULES'):
    if '/snap/code/' in os.environ.get(key, ''):
        os.environ.pop(key, None)
if '/snap/code/' in os.environ.get('XDG_DATA_DIRS', ''):
    os.environ['XDG_DATA_DIRS'] = ':'.join(
        path for path in os.environ['XDG_DATA_DIRS'].split(':') if '/snap/code/' not in path)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / 'eleven-rack-settings.py'
DRIVER_LOGO = ROOT.parent / 'assets' / 'eleven-rack-control-logo-v2.png'
GLib.set_prgname('eleven-rack-control')
GLib.set_application_name('Eleven Rack Control')
spec = importlib.util.spec_from_file_location('settings', BACKEND)
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)

CSS = b'''
.eleven-rack-panel { font-size: 12px; background: #101010; color: #eee9e3; }
.eleven-rack-panel label { color: #eee9e3; }
.eleven-rack-panel .eyebrow { color: #ff8a28; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
.eleven-rack-panel .title { font-size: 24px; font-weight: bold; }
.eleven-rack-panel .subtitle { color: #a39c93; font-size: 12px; }
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
'''


def label(text, style=None):
    widget = Gtk.Label(label=text, xalign=0)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def box(vertical=True, spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                   spacing=spacing)


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
        self.polling_lock = False
        self.event_process = None
        self.event_card = None
        self.events_pending = False
        self.connect('destroy', self.stop_control_events)
        self.updating = False
        self.confirmed = {'clock': None, 'rate': None, 'rig-input': None, 'buffer': None}
        self.polling_buffer = False
        self.buttons = []
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        scroll = Gtk.ScrolledWindow()
        self.add(scroll)
        body = box(spacing=12)
        body.get_style_context().add_class('eleven-rack-panel')
        body.set_border_width(16)
        scroll.add(body)
        header = box(False, 12)
        self.driver_logo = Gtk.Image.new_from_pixbuf(logo)
        self.driver_logo.set_valign(Gtk.Align.CENTER)
        self.driver_logo.get_accessible().set_name('Eleven Rack Control logo')
        header.pack_start(self.driver_logo, False, False, 0)
        identity = box(spacing=3)
        identity.pack_start(label('ELEVEN RACK  /  LINUX', 'eyebrow'), False, False, 0)
        identity.pack_start(label('Eleven Rack Control', 'title'), False, False, 0)
        identity.pack_start(label('Audio routing and hardware settings', 'subtitle'), False, False, 0)
        header.pack_start(identity, True, True, 0)
        self.connection = label('Checking device…', 'badge')
        self.connection.set_valign(Gtk.Align.CENTER)
        header.pack_end(self.connection, False, False, 0)
        body.pack_start(header, False, False, 0)

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
        self.rate = self.choice(clock_card, 'Internal sample rate', [(str(r), f'{r / 1000:g} kHz') for r in settings.RATES])
        self.rate.set_active_id('48000')
        self.rate_status = label('Device stream idle', 'subtitle')
        clock_card.pack_start(self.rate_status, False, False, 0)
        self.buffer = self.choice(clock_card, 'Buffer size · PipeWire',
                                  [(str(n), 'Automatic' if n == 0 else f'{n} samples') for n in settings.BUFFERS])
        self.buffer.set_active(-1)
        self.buffer_status = label('Reading buffer size…', 'subtitle')
        clock_card.pack_start(self.buffer_status, False, False, 0)
        clock_card.pack_start(label('Applies to the shared PipeWire audio graph for this session.', 'subtitle'), False, False, 0)
        self.clock_status = label('Hardware status has not been read', 'subtitle')
        clock_card.pack_start(self.clock_status, False, False, 0)
        note = label('Stop audio apps before changing clock or rate.\nYour DAW chooses its streaming sample rate.', 'subtitle')
        note.set_line_wrap(True)
        clock_card.pack_start(note, False, False, 0)
        control_row.pack_start(clock_card, True, True, 0)

        rig_card = self.card('Rig & monitoring')
        names = ('Guitar', 'Re-Amp', 'Microphone', 'Line L', 'Line R', 'Line L + R', 'Digital L', 'Digital R', 'Digital L + R')
        self.rig = self.choice(rig_card, 'Rig Input', list(zip(settings.RIG_INPUTS, names)))
        self.rig.set_active(-1)
        self.rig.set_tooltip_text('Read the current Rig Input, or select one to apply.')
        rig_actions = box(False, 8)
        self.button(rig_actions, 'Read Rig Input', lambda _: self.run(['rig-input']))
        rig_card.pack_start(rig_actions, False, False, 0)
        rig_card.pack_start(label('Hardware monitoring', 'section'), False, False, 0)
        unavailable = Gtk.Button(label='Unavailable — control not identified')
        unavailable.set_sensitive(False)
        rig_card.pack_start(unavailable, False, False, 0)
        note = label('Direct rig monitoring remains controlled by the Rack.\nA monitoring toggle needs protocol verification.', 'subtitle')
        note.set_line_wrap(True)
        rig_card.pack_start(note, False, False, 0)
        control_row.pack_start(rig_card, True, True, 0)
        body.pack_start(control_row, False, False, 0)

        channels = box(False, 12)
        for heading, entries in [('Inputs · 8 channels', settings.INPUTS), ('Outputs · 6 channels', settings.OUTPUTS)]:
            card = box(spacing=4)
            card.get_style_context().add_class('card')
            card.get_style_context().add_class('channel-card')
            expander = Gtk.Expander(label=heading)
            expander.set_expanded(False)
            rows = box(spacing=2)
            for number, name in enumerate(entries, 1):
                row = box(False, 14)
                row.get_style_context().add_class('channel')
                row.pack_start(label(f'{number:02}', 'number'), False, False, 0)
                row.pack_start(label(name), True, True, 0)
                rows.pack_start(row, False, False, 0)
            expander.add(rows)
            card.pack_start(expander, False, False, 0)
            channels.pack_start(card, True, True, 0)
        body.pack_start(channels, False, False, 0)
        self.message = label('Ready. Choose a setting to apply it.', 'notice')
        self.message.set_line_wrap(True)
        self.message.set_selectable(True)
        body.pack_start(self.message, False, False, 0)
        body.pack_start(label('Experimental driver · 48 kHz recording and playback verified · Settings use ALSA', 'footer'), False, False, 0)
        self.choices = {'clock': self.clock, 'rate': self.rate, 'rig-input': self.rig, 'buffer': self.buffer}
        for command, choice in self.choices.items():
            choice.connect('changed', self.selection_changed, command)
            choice.set_tooltip_text('Selecting a value applies it immediately.')
        self.refresh_connection()
        GLib.timeout_add_seconds(3, self.refresh_connection)
        GLib.timeout_add(250, self.refresh_stream_rate)
        GLib.timeout_add_seconds(2, self.poll_buffer)
        GLib.idle_add(lambda: (self.poll_buffer(), False)[1])
        # Establish a real rollback value before the first clock selection.
        GLib.idle_add(self.run, ['status'])

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
        try:
            number = settings.card()
            connected = True
            audio = Path(f'/proc/asound/card{number}/stream0').exists()
            self.connection.set_text('Connected · USB audio' if audio else 'Connected · MIDI only')
            self.start_control_events(number)
        except RuntimeError:
            connected = False
            self.connection.set_text('Disconnected')
            self.set_clock_lock(None)
            self.stop_control_events()
        for button in self.buttons:
            button.set_sensitive(connected and not self.busy)
        for choice in self.choices.values():
            choice.set_sensitive(connected and not self.busy)
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
        return True

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

    def refresh_stream_rate(self):
        if self.busy:
            return True
        try:
            directory = Path('/proc/asound/card%d' % settings.card())
            rates = set()
            for params in directory.glob('pcm*/sub*/hw_params'):
                match = re.search(r'^rate:\s+(\d+)', params.read_text(), re.MULTILINE)
                if match:
                    rates.add(match.group(1))
            if len(rates) == 1:
                value = rates.pop()
                self.rate_status.set_text('Device stream · %s kHz' % (int(value) / 1000))
                if value in tuple(map(str, settings.RATES)):
                    self.updating = True
                    try:
                        self.confirmed['rate'] = value
                        self.rate.set_active_id(value)
                    finally:
                        self.updating = False
            else:
                self.rate_status.set_text('Device stream idle' if not rates else 'Multiple stream rates')
        except (RuntimeError, OSError):
            self.rate_status.set_text('Device stream unavailable')
        return True

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
        def worker():
            try:
                result = subprocess.run([sys.executable, str(BACKEND), 'status'],
                                        capture_output=True, text=True, timeout=8)
                text = result.stdout if result.returncode == 0 else ''
            except (OSError, subprocess.TimeoutExpired):
                text = ''
            GLib.idle_add(self.lock_polled, text)
        threading.Thread(target=worker, daemon=True).start()
        return True

    def lock_polled(self, text):
        self.polling_lock = False
        if not self.busy:
            self.update_clock_lock(text)
            self.updating = True
            try:
                for line in text.splitlines():
                    if line.startswith('Clock: '):
                        value = line.split(': ', 1)[1]
                        if value in settings.CLOCKS:
                            self.confirmed['clock'] = value
                            self.clock.set_active_id(value)
            finally:
                self.updating = False
        return False

    def selection_changed(self, choice, command):
        value = choice.get_active_id()
        if not self.updating and value is not None:
            self.run([command, value])

    def poll_buffer(self):
        if self.busy or self.polling_buffer:
            return True
        self.polling_buffer = True
        def worker():
            try:
                result = subprocess.run([sys.executable, str(BACKEND), 'buffer'],
                                        capture_output=True, text=True, timeout=6)
                text = result.stdout if result.returncode == 0 else ''
            except (OSError, subprocess.TimeoutExpired):
                text = ''
            GLib.idle_add(self.buffer_polled, text)
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
                        self.confirmed['buffer'] = value
                        self.buffer.set_active_id(value)
                    elif line.startswith('Buffer duration: '):
                        self.buffer_status.set_text(line.split(': ', 1)[1])
                if not text:
                    self.buffer_status.set_text('PipeWire buffer status unavailable')
            finally:
                self.updating = False
        return False

    def run(self, command):
        if self.busy or any(part is None for part in command):
            return
        self.busy = True
        if command[0] == 'clock':
            self.set_clock_lock(None)
        self.refresh_connection()
        self.message.set_text('Reading hardware…' if len(command) == 1 else 'Applying setting…')
        def worker():
            try:
                invocation = [sys.executable, str(BACKEND), *command]
                result = subprocess.run(invocation, capture_output=True, text=True, timeout=120)
                text = result.stdout.strip() if result.returncode == 0 else result.stderr.strip() or 'Authentication cancelled or setting not applied.'
                success = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired) as error:
                text, success = str(error), False
            GLib.idle_add(self.finished, command, text, success)
        threading.Thread(target=worker, daemon=True).start()

    def finished(self, command, text, success):
        self.busy = False
        self.message.set_text(text)
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
                    elif line.startswith('Buffer duration: '):
                        self.buffer_status.set_text(line.split(': ', 1)[1])
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
        self.refresh_connection()
        if len(command) > 1 or self.events_pending:
            self.events_pending = False
            self.poll_clock_lock()
        return False


if __name__ == '__main__':
    window = Panel()
    window.show_all()
    Gtk.main()
