"""Exercise Control's stream lifecycle without requiring a GTK display."""
import ast
import fcntl
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

source = ast.parse((Path(__file__).resolve().parents[1] / 'eleven-rack-panel.py').read_text())
panel = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'Panel')
methods = [node for node in panel.body if isinstance(node, ast.FunctionDef) and node.name in ('refresh_meters', 'meters_updated')]
namespace = {'Path': Path, 'os': os, 'fcntl': fcntl}
exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), '<panel lifecycle>', 'exec'), namespace)


class PanelStreamLifecycleTest(unittest.TestCase):
    def panel(self, expanded=False, **overrides):
        values = dict(meter_expanders=[SimpleNamespace(get_expanded=lambda: expanded)],
                      busy=False, meters_suspended=False, meter_process=SimpleNamespace(poll=lambda: None),
                      meter_starting=False, meter_epoch=3, meter_widgets=[], stop_meters=Mock(),
                      meter_display_db=[-60.0] * 16)
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_collapsing_keeps_live_duplex_client(self):
        for expanded in (True, False):
            panel = self.panel(expanded)
            with patch.object(Path, 'exists', return_value=False):
                self.assertTrue(namespace['refresh_meters'](panel))
            panel.stop_meters.assert_not_called()

    def test_busy_or_suspended_still_releases_client(self):
        for state in ({'busy': True}, {'meters_suspended': True}):
            panel = self.panel(**state)
            with patch.object(Path, 'exists', return_value=False):
                self.assertTrue(namespace['refresh_meters'](panel))
            panel.stop_meters.assert_called_once()

    def test_hidden_meters_skip_widget_updates(self):
        meter, readout = Mock(), Mock()
        panel = self.panel(meter_widgets=[(meter, readout)])
        self.assertFalse(namespace['meters_updated'](panel, [0.5] * 14, 3))
        meter.set_value.assert_not_called()
        readout.set_text.assert_not_called()


if __name__ == '__main__':
    unittest.main()
