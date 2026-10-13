#!/usr/bin/env python3
"""Prepare one native Arch editor package from electron-builder's unpacked application."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def prepare(unpacked, output):
    version = (ROOT / 'VERSION').read_text().strip().replace('~', '')
    if not re.fullmatch(r'[0-9][A-Za-z0-9_.+]*', version):
        raise RuntimeError('Unsupported package version')
    for name in ('eleven-rack-editor-linux', 'chrome-sandbox', 'resources/app.asar', 'resources/eleven-rack-updates.py',
                 'resources/bridge-linux/bridge.py', 'resources/bridge-linux/segmented_sysex.py',
                 'resources/eleven-rack-editor-logo.png', 'resources/LICENSE', 'resources/NOTICE'):
        if not (unpacked / name).is_file():
            raise RuntimeError(f'Incomplete unpacked editor: missing {name}')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'eleven-rack-editor.tar.gz'
    with tempfile.TemporaryDirectory(prefix='arch-editor-') as directory:
        payload = Path(directory) / 'eleven-rack-editor'
        shutil.copytree(unpacked, payload, symlinks=True)
        launcher = payload / 'arch-launcher'
        launcher.write_text('#!/bin/sh\nexec env -u ELECTRON_RUN_AS_NODE -u GSETTINGS_SCHEMA_DIR '
                            '-u GTK_PATH -u GIO_EXTRA_MODULES '
                            '/opt/eleven-rack-editor/eleven-rack-editor-linux "$@"\n')
        launcher.chmod(0o755)
        (payload / 'arch.desktop').write_text('''[Desktop Entry]
Type=Application
Name=Eleven Rack Editor
Comment=Edit Eleven Rack rigs
Exec=eleven-rack-editor-linux
Icon=/opt/eleven-rack-editor/resources/eleven-rack-editor-logo.png
Terminal=false
Categories=AudioVideo;Audio;
''')
        with tarfile.open(archive, 'w:gz') as bundle:
            bundle.add(payload, arcname='eleven-rack-editor')
    recipe = (ROOT / 'packaging/arch/editor.PKGBUILD').read_text()
    recipe = recipe.replace('@VERSION@', version).replace(
        '@EDITOR_SHA256@', hashlib.sha256(archive.read_bytes()).hexdigest())
    (output / 'PKGBUILD').write_text(recipe)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unpacked-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/arch-editor')
    args = parser.parse_args()
    print(prepare(args.unpacked_dir.resolve(), args.output.resolve()))
