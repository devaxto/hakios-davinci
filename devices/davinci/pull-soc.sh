#!/bin/bash
# Pull the phone's own device tree over adb and turn it into the SoC boot-args HakiOS needs on this
# device (tools/soc-args.py). Unlike the POCO's, davinci's soc.args carries real addresses: the
# kernel's modem and IPA defaults are redwood's. Needs the phone in Android with adb (root not
# required: /sys/firmware/fdt is world-readable).
set -e
cd "$(dirname "$0")/../.."
PATH=$PWD/tools/macos-bin/platform-tools:$PATH
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
adb pull /sys/firmware/fdt "$tmp/fdt" >/dev/null || { echo "pull-soc.sh: cannot read /sys/firmware/fdt over adb"; exit 1; }
# Keep the tree itself as well: the same file is what build-davinci-dtb.py and the port's notes
# need (reserved-memory regions, GIC, the timer's interrupt), and adb will not always be there.
cp "$tmp/fdt" "$(dirname "$0")/fdt.local"
tools/soc-args.py "$tmp/fdt" | tee "$(dirname "$0")/soc.args"
# The same tree again, read as facts instead of boot-args: the timer's interrupt, the cores and which
# of them are the slow ones, the GIC, the panel, the touch, storage, the GPU, the PMICs. This is
# what devices/<name>/device.conf and the loader's platform are waiting for.
tools/fdt-facts.py "$tmp/fdt" --device "$(basename "$(dirname "$0")")"
echo "pull-soc.sh: wrote $(dirname "$0")/soc.args and fdt.local"
