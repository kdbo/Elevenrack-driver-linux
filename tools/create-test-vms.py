#!/usr/bin/env python3
"""Create powered-off VirtualBox package-test VMs; never capture host USB devices."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--machine', choices=('ElevenRack-Arch', 'ElevenRack-CentOS-Stream10'))
    args = parser.parse_args()
    directory = args.directory.resolve()
    machines = [('ElevenRack-Arch', 'ArchLinux_64'),
                ('ElevenRack-CentOS-Stream10', 'RedHat_64')]
    if args.machine:
        machines = [entry for entry in machines if entry[0] == args.machine]
    if args.execute:
        existing = subprocess.check_output(['VBoxManage', 'list', 'vms'], text=True)
        for name, _ in machines:
            if '"' + name + '"' in existing or (directory / name).exists():
                parser.error('VM already exists; refusing to overwrite: ' + name)
        directory.mkdir(parents=True, exist_ok=True)
    for name, os_type in machines:
        disk = directory / name / (name + '.vdi')
        commands = [
            ['VBoxManage', 'createvm', '--name', name, '--ostype', os_type,
             '--basefolder', str(directory), '--register'],
            ['VBoxManage', 'modifyvm', name, '--memory', '3072', '--cpus', '2',
             '--graphicscontroller', 'vmsvga', '--vram', '128', '--firmware', 'efi',
             '--nic1', 'nat', '--boot1', 'dvd', '--boot2', 'disk'],
            ['VBoxManage', 'createmedium', 'disk', '--filename', str(disk),
             '--size', '40960', '--format', 'VDI', '--variant', 'Standard'],
            ['VBoxManage', 'storagectl', name, '--name', 'SATA', '--add', 'sata',
             '--controller', 'IntelAhci'],
            ['VBoxManage', 'storageattach', name, '--storagectl', 'SATA',
             '--port', '0', '--device', '0', '--type', 'hdd', '--medium', str(disk)],
            ['VBoxManage', 'storageattach', name, '--storagectl', 'SATA',
             '--port', '1', '--device', '0', '--type', 'dvddrive', '--medium', 'emptydrive'],
        ]
        for command in commands:
            if args.execute:
                subprocess.run(command, check=True)
            else:
                print(command)


if __name__ == '__main__':
    main()
