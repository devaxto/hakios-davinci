#!/usr/bin/env python3
"""Build a complete davinci DTB from a local SM7150 downstream tree, and report the facts the port
needs out of it (model, board id, cores, GIC, timer interrupt, framebuffer region, touch).

  tools/build-davinci-dtb.py [KERNEL-TREE]

Writes out/davinci/davinci.dtb, the .dts it was made from, and davinci.dtb.facts -- which holds the
`gic_timer_irq=` for devices/davinci/device.conf. The tree is not modified.

Written after tools/build-raphael-dtb.py: the shape is raphael's, the values are read out of
davinci's own tree rather than asserted from raphael's.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('kernel', nargs='?', type=Path, default=Path.home() / 'kernel/davinci',
                help='the SM7150 Android kernel tree (default: %(default)s)')
ap.add_argument('-o', '--output', type=Path, default=ROOT / 'out/davinci/davinci.dtb')
ap.add_argument('--base', default='sm7150', help='base .dts without extension (default: %(default)s)')
ap.add_argument('--overlay', default='davinci-sm7150-overlay',
                help="the -overlay .dts to merge, '' for none (default: %(default)s)")
ap.add_argument('--expect', action='append', default=[], metavar='KEY=VALUE',
                help='also require a fact to have this value (e.g. gic_timer_irq=30)')
args = ap.parse_args()
src = args.kernel.resolve()
dts = src / 'arch/arm64/boot/dts/qcom'
dtc = os.environ.get('DTC', str(src / 'out/scripts/dtc/dtc'))
merge = os.environ.get('FDTOVERLAY', str(src / 'out/scripts/dtc/fdtoverlay'))
output = args.output.resolve()


def die(what):
    raise SystemExit(f'build-davinci-dtb: {what}')


def node_prop(tree, node_pattern, prop):
    """The cells of `prop` in the first node whose header matches `node_pattern` (None if absent)."""
    found = re.search(node_pattern + r' \{[^}]*?' + prop + r' = <([^>]*)>;', tree, re.S)
    return ' '.join(found.group(1).split()) if found else None


if not dts.is_dir():
    die(f'no tree at {dts}\n  the DTS files live in arch/arm64/boot/dts/qcom of the SM7150 kernel')
if not Path(dtc).exists():
    die(f'no dtc at {dtc}\n  build the tree first (make dtbs), or set DTC=/path/to/dtc')
names = [args.base] + ([args.overlay] if args.overlay else [])
for name in names:
    if not (dts / (name + '.dts')).exists():
        have = sorted(p.name for p in dts.glob('*davinci*')) + sorted(p.name for p in dts.glob('sm7150*'))
        die(f'no {dts / (name + ".dts")}\n  this tree has: ' + (', '.join(have) or '(neither davinci nor sm7150)')
            + '\n  pass --base and --overlay to name them')

output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='hackios-davinci-dtb-') as tmp:
    work = Path(tmp)
    made = []
    with output.with_name(output.name + '.build.log').open('w') as log:
        for name in names:
            preprocessed = work / (name + '.dts')
            subprocess.run([os.environ.get('HOSTCC', 'gcc'), '-E', '-nostdinc', '-undef', '-D__DTS__',
                            '-x', 'assembler-with-cpp', '-I', str(src / 'scripts/dtc/include-prefixes'),
                            '-o', str(preprocessed), str(dts / (name + '.dts'))], check=True)
            if name != args.base:
                # Android's root metadata also needs a fragment when using libfdt's overlay merger.
                preprocessed.write_text(re.sub(r'(?m)^(\s*)/\s*\{', r'\1&{/} {', preprocessed.read_text()))
            subprocess.run([dtc, '-@', '-I', 'dts', '-O', 'dtb', '-b', '0', '-i', str(dts),
                            '-o', str(work / (name + '.dtb')), str(preprocessed)], stderr=log, check=True)
            made.append(work / (name + '.dtb'))
    merged = made[0]
    for i, overlay in enumerate(made[1:], start=1):
        out = work / f'merged{i}.dtb'
        subprocess.run([merge, '-i', str(merged), '-o', str(out), str(overlay)], check=True)
        merged = out
    tree = subprocess.check_output([dtc, '-q', '-I', 'dtb', '-O', 'dts', str(merged)], text=True)

    # A base-only tree or a half-merged overlay is not a phone DTB.
    if '__fixups__ {' in tree or '__local_fixups__ {' in tree:
        die('the overlay was not merged: the tree still has __fixups__')

    model = re.search(r'(?m)^\s*model = "([^"]*)";', tree)
    model = model.group(1) if model else ''
    if 'davinci' not in model.lower():
        die(f'model is "{model}", which does not name davinci')

    cpus = sorted(re.findall(r'\bcpu@([0-9a-f]+) \{\s*device_type = "cpu";', tree))

    # The architectural timer's virtual PPI: its GIC INTID is 16 + the PPI number. The loader cannot
    # work that out, and the kernel's default (27) is only right on some SoCs -- raphael's is 19.
    timer = re.search(r'compatible = "arm,armv8-timer"[^}]*?interrupts = <([^>]*)>;', tree, re.S)
    gic_timer_irq = None
    if timer:
        cells = [int(cell, 0) for cell in timer.group(1).replace(',', ' ').split()]
        ppis = cells[1::3]                       # type, number, flags
        if len(ppis) > 1:                        # secure physical, non-secure physical, virtual, ...
            gic_timer_irq = 16 + ppis[1]

    board = re.search(r'qcom,board-id = <([^>]*)>;', tree)
    facts = {
        'model': model,
        'board-id': ' '.join(board.group(1).split()) if board else 'unknown',
        'cpus': ' '.join(cpus),
        'gic': node_prop(tree, r'interrupt-controller@[0-9a-f]+', 'reg') or 'unknown',
        'gic_timer_irq': str(gic_timer_irq) if gic_timer_irq is not None else 'unknown',
        'framebuffer': node_prop(tree, r'(?:framebuffer|cont_splash[^ ]*|splash[^ ]*)@[0-9a-f]+', 'reg') or 'unknown',
        'touch': ' '.join(sorted(set(re.findall(r'compatible = "((?:goodix|focaltech|novatek|synaptics)[^"]*)";', tree)))) or 'unknown',
    }
    if len(cpus) != 8:
        die(f'{len(cpus)} cpu nodes in the device tree, expected 8')
    if gic_timer_irq is None:
        print('build-davinci-dtb: the timer has no interrupts property; gic_timer_irq stays unknown')
    for want in args.expect:
        key, _, value = want.partition('=')
        if facts.get(key) != value:
            die(f'expected {key}={value}, the tree says {facts.get(key)!r}')

    output.with_suffix('.dts').write_text(tree)
    output.write_bytes(merged.read_bytes())

output.with_name(output.name + '.facts').write_text(''.join(f'{k}={v}\n' for k, v in facts.items()))
revision = subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip()
output.with_suffix('.source').write_text(f'{src}\n{revision}\n')
print(f'{output}: {output.stat().st_size} bytes')
for key, value in facts.items():
    print(f'  {key}: {value}')
print(f'  -> devices/davinci/device.conf BOOTARGS wants gic_timer_irq={facts["gic_timer_irq"]}')
