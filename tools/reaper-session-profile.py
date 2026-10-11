#!/usr/bin/env python3
"""Prepare an isolated REAPER resource directory for calibrated Line In L."""
import configparser
from pathlib import Path
import shutil
import tempfile


def prepare(directory, correction, source=None):
    directory = Path(directory)
    if not 0 <= correction <= 8192:
        raise ValueError('Invalid session correction')
    source = Path(source or Path.home()/'.config/REAPER')
    marker = directory/'.eleven-rack-profile'
    if not directory.exists():
        if not (source/'reaper.ini').is_file():
            raise RuntimeError('REAPER configuration missing')
        directory.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.reaper-profile-', dir=directory.parent))
        try:
            shutil.copytree(source, temporary, dirs_exist_ok=True)
            (temporary/'.eleven-rack-profile').write_text('Calibrated Line In L only\n')
            temporary.rename(directory)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if not marker.is_file():
        raise RuntimeError('Refusing to modify an unowned REAPER profile')
    config = directory/'reaper.ini'
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    parser.read(config)
    if not parser.has_section('REAPER'):
        raise RuntimeError('Invalid REAPER profile')
    parser.set('REAPER', 'adjreclat', '1')
    parser.set('REAPER', 'adjrecmanlatin', str(correction))
    parser.set('REAPER', 'adjrecmanlat', '0')
    temporary = config.with_suffix('.ini.new')
    with temporary.open('w') as output:
        parser.write(output, space_around_delimiters=False)
    temporary.replace(config)
    return config
