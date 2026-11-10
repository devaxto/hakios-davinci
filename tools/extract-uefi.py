#!/usr/bin/env python3
"""Extract a phone's AArch64 UEFI modules out of its own XBL, and apply that device's byte-checked
firmware fixes if it has any.

  tools/extract-uefi.py --device raphael
  tools/extract-uefi.py --device davinci --xbl out/davinci/firmware/xbl.img

Per device (devices/<name>/uefi/):
  xbl.sha256                     optional, one line: the XBL build the fixes below were checked on
  <name>-firmware-patches.json   optional, in the shape of raphael's (DAL, USB, buttons)

Writes Mu-Silicium/Binaries/<name>/ (modules, .inf/.depex, RawFiles), plus manifest.json and
patches.json. Needs uefi_firmware in out/host-python (pip install uefi_firmware).
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--device', default='raphael', help='the device directory the port lives in (default: %(default)s)')
ap.add_argument('--xbl', type=Path, help='the XBL image (default: out/<device>/firmware/xbl.img)')
ap.add_argument('--out', type=Path, help='where the modules go (default: Mu-Silicium/Binaries/<device>)')
ap.add_argument('--expect-sha256', help="refuse an XBL that is not this one (default: devices/<device>/uefi/xbl.sha256)")
ap.add_argument('--no-patches', action='store_true', help='extract only: do not apply the firmware fixes')
args = ap.parse_args()
device = args.device
uefi_dir = ROOT / 'devices' / device / 'uefi'
source = args.xbl or (ROOT / f'out/{device}/firmware/xbl.img')
out = args.out or (ROOT / 'Mu-Silicium' / 'Binaries' / device)

sys.path.insert(0, str(ROOT / 'out/host-python'))
try:
    from uefi_firmware.uefi import FirmwareVolume, FirmwareFile, FirmwareFileSystemSection
except ImportError:
    raise SystemExit('extract-uefi: no uefi_firmware in out/host-python (pip install uefi_firmware, see README)')


def die(what):
    raise SystemExit(f'extract-uefi: {what}')


if not source.is_file():
    die(f'no XBL at {source}\n  it comes off the phone (tools/ufs-read.py) -- not from another device')
raw = source.read_bytes()
digest = hashlib.sha256(raw).hexdigest()

# The fixes are byte offsets into one exact build of the firmware: an XBL that is even slightly
# different makes them silently wrong, so the image itself is what gets checked.
pinned_file = uefi_dir / 'xbl.sha256'
expected = args.expect_sha256 or (pinned_file.read_text().split()[0] if pinned_file.is_file() else None)
if expected and expected != digest:
    die(f'{source} is not the XBL this port was made against\n  expected {expected}\n  this one {digest}')
if not expected:
    print(f'extract-uefi: {device} has no pinned XBL; this one is {digest}\n'
          f'  devices/{device}/uefi/xbl.sha256 does not exist yet (nothing to check the fixes against)')

fv = FirmwareVolume(raw[raw.index(b'_FVH') - 40:])
assert fv.valid_header and fv.process()
out.mkdir(parents=True, exist_ok=True)


def walk(obj):
    yield obj
    for child in obj.objects:
        if child is not None:
            yield from walk(child)


def sections(obj):
    for child in obj.objects:
        if child is None or isinstance(child, FirmwareFile):
            continue
        if isinstance(child, FirmwareFileSystemSection):
            yield child
        yield from sections(child)


records = []
types = {3: 'SEC', 4: 'PEI_CORE', 5: 'DXE_CORE', 6: 'PEIM', 7: 'DXE_DRIVER',
         9: 'UEFI_APPLICATION', 12: 'DXE_SMM_DRIVER'}
for f in (obj for obj in walk(fv) if isinstance(obj, FirmwareFile)):
    sec = list(sections(f))
    names = [s.name for s in sec if s.type == 0x15 and s.name]
    if f.type == 2 and names:
        data = next((s.data for s in sec if s.type == 0x19), None)
        if data is not None:
            name = Path(names[0].replace('\\', '/'))
            assert not name.is_absolute() and '..' not in name.parts
            dest = out / 'RawFiles' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    if f.type not in types:
        continue
    exe = next((s for s in sec if s.type in (0x10, 0x12)), None)
    if exe is None:
        continue
    code = exe.data
    if exe.type == 0x12:
        assert code[:2] == b'VZ' and struct.unpack_from('<H', code, 2)[0] == 0xaa64
    else:
        offset = struct.unpack_from('<I', code, 0x3c)[0]
        assert code[offset:offset + 4] == b'PE\0\0'
        assert struct.unpack_from('<H', code, offset + 4)[0] == 0xaa64
    paths = [p.decode().replace('\\', '/') for p in re.findall(rb'[a-zA-Z/\\0-9_\-\.]*\.dll\b', code)]
    pdb = next(p.split('/AARCH64/')[-1] for p in paths if '/AARCH64/' in p)
    parts = pdb.split('/')
    module, relative = parts[-3], Path(*parts[:-3])
    assert not relative.is_absolute() and '..' not in relative.parts
    dest = out / relative
    dest.mkdir(parents=True, exist_ok=True)
    (dest / (module + '.efi')).write_bytes(code)
    depex = next((s.data for s in sec if s.type in (0x13, 0x1b, 0x1c)), None)
    inf = (f'[Defines]\n  INF_VERSION = 0x0001001B\n  BASE_NAME = {module}\n'
           f'  FILE_GUID = {f.guid_label}\n  MODULE_TYPE = {types[f.type]}\n'
           f'  VERSION_STRING = 1.0\n\n[Binaries.AARCH64]\n'
           f'  {"TE" if exe.type == 0x12 else "PE32"}|{module}.efi|*\n')
    if depex is not None:
        (dest / (module + '.depex')).write_bytes(depex)
        inf += f'  DXE_DEPEX|{module}.depex|*\n'
    (dest / (module + '.inf')).write_text(inf)
    records.append({'name': module, 'inf': str(relative / (module + '.inf')),
                    'sha256': hashlib.sha256(code).hexdigest()})

patches = []
patches_file = uefi_dir / f'{device}-firmware-patches.json'
if args.no_patches:
    print(f'extract-uefi: --no-patches: {patches_file.name} not applied')
elif not patches_file.is_file():
    print(f'extract-uefi: {device} has no {patches_file.name}\n'
          '  the modules are as the vendor built them: DAL, USB and the buttons are expected to need '
          'this phone\'s own fixes before the loader can rely on them')
else:
    patches = json.loads(patches_file.read_text())
    for patch in patches:
        matches = list(out.glob('**/' + patch['module'] + '.efi'))
        assert len(matches) == 1, patch['module']
        dest = matches[0]
        code = bytearray(dest.read_bytes())
        assert hashlib.sha256(code).hexdigest() == patch['original_sha256'], dest
        for offset, old, new in patch['changes']:
            assert code[offset] == old, (dest, offset)
            code[offset] = new
        assert hashlib.sha256(code).hexdigest() == patch['patched_sha256'], dest
        dest.write_bytes(code)
    (out / 'patches.json').write_text(json.dumps(patches, indent=2) + '\n')

(out / 'manifest.json').write_text(json.dumps({'device': device, 'xbl': str(source), 'xbl_sha256': digest,
                                               'modules': records}, indent=2) + '\n')
print(f'{len(records)} AArch64 modules extracted to {out}'
      + (f'; {len(patches)} firmware fixes verified' if patches else '; no firmware fixes applied'))
