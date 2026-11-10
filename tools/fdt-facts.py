#!/usr/bin/env python3
"""Read a phone's own device tree and print the facts a port needs, named the way the port asks
for them.

usage: tools/fdt-facts.py [FDT] [--device NAME] [--expect KEY=VALUE ...]

The tree is the one /sys/firmware/fdt holds and devices/<name>/pull-soc.sh keeps as fdt.local.
This is the read-only half of "what does this phone have": it writes nothing, changes nothing, and
copies no part of the tree. The other half is tools/soc-args.py, which turns the same file into the
soc_* boot arguments the modem and IPA drivers take.

What it answers, in the order a port needs it: who the phone is, how many cores and which are the
slow ones, the GIC and the timer's interrupt, the panel, the touch controller, storage, the GPU,
the PMICs and the keys, the radio, and the memory reservations a driver has to be told about.
"""
import argparse
import importlib.util
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# one parser for both tools: soc-args.py already reads the flattened tree, and a second copy of
# that loop would be a second thing to get wrong
spec = importlib.util.spec_from_file_location('soc_args', Path(__file__).with_name('soc-args.py'))
soc_args = importlib.util.module_from_spec(spec)
spec.loader.exec_module(soc_args)

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('fdt', nargs='?', type=Path, help='the tree (default: devices/<device>/fdt.local)')
ap.add_argument('--device', default='davinci', help='the device directory to read the tree from (default: %(default)s)')
ap.add_argument('--expect', action='append', default=[], metavar='KEY=VALUE',
                help='fail unless a fact has this value (gic_timer_irq, cpus, small_cores, gic_dist, ...)')
args = ap.parse_args()

source = args.fdt or ROOT / 'devices' / args.device / 'fdt.local'
if not source.is_file():
    raise SystemExit(f'fdt-facts.py: no tree at {source}\n'
                     f'  devices/{args.device}/pull-soc.sh keeps the phone\'s own as fdt.local')
try:
    nodes = soc_args.nodes_of(source.read_bytes())
except SystemExit as why:
    raise SystemExit(f'fdt-facts.py: {source}: {why}')


# -- reading the tree ------------------------------------------------------------

def u32(value, index=0):
    return struct.unpack_from('>I', value, index * 4)[0]


def u64(value, index=0):
    return struct.unpack_from('>Q', value, index * 8)[0]


def strings(props, name):
    return [s.decode() for s in props.get(name, b'').split(b'\0') if s]


def leaf(path):
    return path.rsplit('/', 1)[-1]


def parent(path):
    return path.rsplit('/', 1)[0] if '/' in path else ''


def cells(nodes, path):
    """The #address-cells and #size-cells `reg` is counted in: its parent's, not its own."""
    props = nodes.get(parent(path), {})
    return u32(props.get('#address-cells', b'\0\0\0\2')), u32(props.get('#size-cells', b'\0\0\0\2'))


def regions(nodes, path):
    props = nodes.get(path, {})
    if 'reg' not in props:
        return []
    ac, sc = cells(nodes, path)
    if not ac or not sc:
        return []
    value, step, out = props['reg'], (ac + sc) * 4, []
    for at in range(0, len(value) - len(value) % step, step):
        base = size = 0
        for i in range(ac):
            base = (base << 32) | u32(value, at // 4 + i)
        for i in range(sc):
            size = (size << 32) | u32(value, at // 4 + ac + i)
        out.append((base, size))
    return out


def named_regions(nodes, path):
    regs = regions(nodes, path)
    names = strings(nodes.get(path, {}), 'reg-names')
    return list(zip(names, regs)) if len(names) == len(regs) else [(f'[{i}]', r) for i, r in enumerate(regs)]


def gic_cells(nodes):
    for props in nodes.values():
        if 'interrupt-controller' in props and '#interrupt-cells' in props:
            return u32(props['#interrupt-cells'])
    return 3


def interrupts(nodes, path):
    props = nodes.get(path, {})
    if 'interrupts' not in props:
        return []
    count, value = gic_cells(nodes), props['interrupts']
    return [[u32(value, at // 4 + i) for i in range(count)]
            for at in range(0, len(value) - len(value) % (4 * count), 4 * count)]


def irq_name(spec):
    kind, number = spec[0], spec[1]
    kind_name = {0: 'SPI', 1: 'PPI', 2: 'SGI', 4: 'LPI'}.get(kind, f'type {kind}')
    absolute = number + (32 if kind == 0 else 16 if kind == 1 else 0)
    return f'{kind_name} {number} (IRQ {absolute})'


def first_with(nodes, *props):
    for path, node in nodes.items():
        if any(p in node for p in props):
            return path, node
    return None, {}


def first_of(nodes, compatible):
    for path, node in nodes.items():
        if compatible in strings(node, 'compatible'):
            return path, node
    return None, {}


def containing(nodes, *needles):
    """Every node whose compatible names one of these (a substring: 'gt9xxx' covers gt9886)."""
    return [(path, node) for path, node in nodes.items()
            if any(n in c for c in strings(node, 'compatible') for n in needles)]


def fact(name, value):
    FACTS[name] = value
    return value


FACTS = {}


def put(label, value, note=''):
    print(f'  {label}{" " * max(1, 20 - len(label))}{value}' + (f'   {note}' if note else ''))


def where(text):
    print(f'{text}\n')


def hexes(region):
    base, size = region
    return f'{base:#x} +{size:#x}'


# -- who the phone is ------------------------------------------------------------

where(f'{source}')
root = nodes.get('', {})
model = strings(root, 'model')[0] if strings(root, 'model') else '?'
put('model', fact('model', model))
put('compatible', ', '.join(strings(root, 'compatible')) or '-')
for name in ('qcom,board-id', 'qcom,msm-id', 'qcom,pmic-id'):
    if name in root:
        put(name, ' '.join(f'{u32(root[name], i):#x}' for i in range(len(root[name]) // 4)))
symbols = [n for n in ('__symbols__', '__fixups__', '__local_fixups__') if n in nodes]
put('symbols', ', '.join(symbols) if symbols else 'none (a stock tree: no -@ needed, no fixups)')
where('')

chosen = nodes.get('chosen', {})
if strings(chosen, 'bootargs'):
    put('bootargs', ' '.join(strings(chosen, 'bootargs')))
    where('')

# -- the cores -------------------------------------------------------------------

cpus = sorted((path, node) for path, node in nodes.items()
              if leaf(path).startswith('cpu@') and parent(path).lstrip('/') == 'cpus')
print(f'{len(cpus)} cores')
capacities = {}
for path, node in cpus:
    # Qualcomm numbers a core in the second affinity field of its MPIDR (0x100 * core), upstream a
    # plain index: the low word of reg is one of those, and the loader's core_shift decides which
    reg = u32(node['reg'], len(node['reg']) // 4 - 1) if 'reg' in node else int(leaf(path).split('@')[1], 16)
    number = reg >> 8 if reg and reg % 0x100 == 0 else reg
    capacity = node.get('capacity-dmips-mhz', node.get('qcom,capacity-dmips-mhz'))
    capacities[number] = u32(capacity) if capacity else None
    put(f'cpu{number}', ', '.join(strings(node, 'compatible')) or '-',
        f'capacity {capacities[number]}' if capacities[number] else '')
put('cpus', fact('cpus', len(cpus)))
if any(capacities.values()):
    # the slower cluster is the one below nine tenths of the fastest core: two cores of the same
    # kind read 1023 and 1024 in the trees seen so far, and a little cluster is never that close
    # (406 against 1024 on redwood, 1024 against 1740 on davinci)
    fastest = max(c for c in capacities.values() if c)
    small = sum(1 << number for number, c in capacities.items() if c and c * 10 < fastest * 9)
    put('small_cores', fact('small_cores', f'{small:#04x}'), 'the slower cores (loader: platform->small_cores)')
where('')

# -- the interrupt controller and the timer --------------------------------------

path, gic = first_with(nodes, 'interrupt-controller')
if gic:
    print(f'GIC  {path or "/"}')
    for name, region in named_regions(nodes, path):
        put(name, hexes(region))
    regs = regions(nodes, path)
    if regs:
        fact('gic_dist', f'{regs[0][0]:#x}')
        if len(regs) > 1:
            fact('gic_redist', f'{regs[1][0]:#x}')
    where('')

path, timer = first_of(nodes, 'arm,armv8-timer')
if timer:
    print(f'timer  {path}')
    # the Arm binding's order: secure physical, non-secure physical, virtual, hyp
    labels = ('secure-phys', 'non-secure-phys', 'virtual', 'hyp')
    specs = interrupts(nodes, path)
    for i, spec in enumerate(specs):
        put(labels[i] if i < len(labels) else f'[{i}]', irq_name(spec))
    if len(specs) > 2:
        virtual = specs[2][1] + 16 if specs[2][0] == 1 else specs[2][1]
        put('gic_timer_irq', fact('gic_timer_irq', virtual),
            'device.conf BOOTARGS: the virtual timer, PPI + 16')
    else:
        put('gic_timer_irq', '?', 'no virtual timer in this tree: do not guess it')
    where('')

# -- the panel -------------------------------------------------------------------

panels = [(p, n) for p, n in nodes.items()
          if any('panel' in c for c in strings(n, 'compatible'))
          or any(k.startswith('qcom,mdss-dsi-panel') for k in n)]
for path, panel in panels:
    print(f'panel  {path}')
    put('compatible', ', '.join(strings(panel, 'compatible')))
    width = u32(panel['qcom,mdss-dsi-panel-width']) if 'qcom,mdss-dsi-panel-width' in panel else None
    height = u32(panel['qcom,mdss-dsi-panel-height']) if 'qcom,mdss-dsi-panel-height' in panel else None
    if width and height:
        put('size', f'{width} x {height}')
        fact('panel', f'{width}x{height}')
    for name in ('qcom,mdss-dsi-panel-framerate', 'qcom,mdss-dsi-panel-clockrate'):
        if name in panel:
            put(name.replace('qcom,mdss-dsi-panel-', ''), f'{u64(panel[name])}')
    if 'qcom,mdss-dsi-panel-type' in panel:
        kind = u32(panel['qcom,mdss-dsi-panel-type'])
        put('type', kind, '1 = command mode (behind a TE signal), 0 = video mode')
        fact('panel_type', kind)
    tear = sorted(n for n in panel if n.startswith('qcom,mdss-dsi-te'))
    if tear:
        put('tear check', f'{len(tear)} properties')
    where('')

# -- the touch controller --------------------------------------------------------

for path, touch in containing(nodes, 'goodix', 'gt9', 'focaltech', 'ft5', 'synaptics', 'novatek',
                              'himax', 'atmel', 'melfas'):
    if 'interrupts' in touch or 'reg' in touch:
        print(f'touch  {path}')
        put('compatible', ', '.join(strings(touch, 'compatible')))
        put('status', strings(touch, 'status')[0] if strings(touch, 'status') else 'okay')
        regs = regions(nodes, path)
        if regs:
            put('bus', hexes(regs[0]))
        for spec in interrupts(nodes, path):
            put('interrupt', irq_name(spec))
        for name in ('qcom,firmware-name', 'firmware-name'):
            if name in touch:
                put('firmware', strings(touch, name)[0])
        fact('touch', ', '.join(strings(touch, 'compatible'))[:40])
        where('')

# -- storage, the GPU ------------------------------------------------------------

path, ufs = first_of(nodes, 'qcom,ufshc')
if ufs:
    print(f'storage  {path}')
    for name, region in named_regions(nodes, path):
        put(name, hexes(region))
    put('ufs', fact('ufs', f'{regions(nodes, path)[0][0]:#x}' if regions(nodes, path) else '?'))
    where('')

path, gpu = first_of(nodes, 'qcom,kgsl-3d0')
if gpu:
    print(f'GPU  {path}')
    for name, region in named_regions(nodes, path):
        put(name, hexes(region))
    if 'qcom,chipid' in gpu:
        put('chipid', ' '.join(f'{u32(gpu["qcom,chipid"], i):#x}' for i in range(len(gpu['qcom,chipid']) // 4)))
    # the levels sit in bins (qcom,gpu-pwrlevels-0 ... -5), each bin a list of frequencies: the
    # same frequencies several times over, so they are collected and de-duplicated
    freqs = sorted({u32(node['qcom,gpu-freq']) for p, node in nodes.items()
                    if p.startswith(path + '/') and 'qcom,gpu-freq' in node}, reverse=True)
    if freqs:
        put('power levels', ', '.join(f'{f // 1000000} MHz' for f in freqs))
    where('')

# -- the PMICs and the keys ------------------------------------------------------

# a PMIC is a part named in the tree (qcom,pm6150) or a node on the SPMI bus (qcom,spmi-pmic):
# which of the two a tree uses depends on how much of itself the vendor published, so both are
# read -- what the port needs from here is the part numbers and the bus's address
parts = sorted({named for path, node in nodes.items()
                for named in re.findall(r'(?:qcom,)?((?:pm|pmi|pmr|pmc|pmk|smb)[0-9]{4})',
                                        ' '.join(strings(node, 'compatible')) + ' ' + leaf(path))})
path, spmi = first_of(nodes, 'qcom,spmi-pmic-arb')
if parts or spmi:
    print('PMIC')
    if parts:
        put('parts', ', '.join(parts), 'PON and the keys are inside these')
    for name, region in named_regions(nodes, path):
        put(f'spmi {name}', hexes(region))
    where('')

KEYS = {114: 'VOLUMEDOWN', 115: 'VOLUMEUP', 116: 'POWER', 212: 'CAMERA', 213: 'CAMERA_FOCUS'}
keys = []
for path, node in nodes.items():
    if 'linux,code' in node:
        code = u32(node['linux,code'])
        keys.append(f'{strings(node, "label")[0] if strings(node, "label") else leaf(path)}'
                    f' = {KEYS.get(code, code)}')
    # a PMIC's power-on block: the keys are the qcom,pon_N children
    elif leaf(path).startswith('qcom,pon'):
        keys.append(f'{leaf(path)} on {parent(path).rsplit("/", 1)[-1]}')
if keys:
    print('keys')
    for key in keys:
        put('', key)
    where('')

# -- the radio -------------------------------------------------------------------

path, icnss = first_of(nodes, 'qcom,icnss')
if icnss:
    print(f'radio  {path}')
    for name, region in named_regions(nodes, path):
        put(name, hexes(region))
    for name in ('qcom,wlan-msa-memory', 'qcom,smmu-s1-bypass', 'qcom,pas-id'):
        if name in icnss:
            put(name.replace('qcom,', ''), ' '.join(f'{u32(icnss[name], i):#x}'
                                                    for i in range(len(icnss[name]) // 4)))
    if 'iommus' in icnss:
        put('stream', f'{u32(icnss["iommus"], 1):#x}')
    where('')
else:
    # not every Qualcomm Wi-Fi is the ICNSS part: the WCN6/7 ones are a different path entirely,
    # and knowing which one this is before writing a line of driver code is the point
    named = sorted({c for node in nodes.values() for c in strings(node, 'compatible')
                    if c.startswith(('qcom,wcn', 'qcom,cnss'))})
    if named:
        print('radio')
        put('parts', ', '.join(named), 'not an ICNSS part: the Wi-Fi path is not raphael\'s')
        where('')

# -- the memory a driver has to be told about ------------------------------------

reserved = [(path, node) for path, node in nodes.items()
            if parent(path).lstrip('/') == 'reserved-memory']
if reserved:
    print(f'reserved memory  ({len(reserved)} regions)')
    for path, node in reserved:
        regs = regions(nodes, path)
        if regs:
            put(leaf(path), hexes(regs[0]))
    where('')

# -- what the port does with them ------------------------------------------------

print(f'{args.device}  <- these facts')
print(f'  devices/{args.device}/device.conf   BOOTARGS: gic_timer_irq={FACTS.get("gic_timer_irq", "?")} '
      f'cpus={FACTS.get("cpus", "?")}')
print(f'  xnuloader/loader.c              the platform: gic {FACTS.get("gic_dist", "?")}/'
      f'{FACTS.get("gic_redist", "?")}, small_cores {FACTS.get("small_cores", "?")}')
print('  tools/soc-args.py               the soc_* boot arguments (ipa, ipcc, smem, cmd-db, ...)')

failed = []
for wanted in args.expect:
    name, _, value = wanted.partition('=')
    got = FACTS.get(name)
    same = str(got) == value or (isinstance(got, int) and got == int(value, 0))
    if not same:
        failed.append(f'{name}: expected {value}, this tree has {got}')
if failed:
    raise SystemExit('fdt-facts.py: ' + '; '.join(failed))
