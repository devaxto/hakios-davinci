#!/bin/sh
# Check tools/fdt-facts.py against a tree whose answers are already known: the POCO X5 Pro's own
# (devices/poco-x5-pro/prebuilt/device-tree.dtb), whose timer interrupt, core mask and GIC are the
# ones xnuloader's platform_redwood and its device.conf carry. A guard against a change to the
# reader silently changing what a port is told.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
dtb="$root/devices/poco-x5-pro/prebuilt/device-tree.dtb"

python3 "$root/tools/fdt-facts.py" "$dtb" --device poco-x5-pro \
	--expect gic_timer_irq=27 --expect cpus=8 --expect small_cores=0x0f \
	--expect gic_dist=0x17a00000 --expect gic_redist=0x17a60000 \
	--expect ufs=0x1d84000 >/dev/null

# and it must refuse an answer the tree does not give: a reader that agrees with everything would
# pass the check above without reading anything
if python3 "$root/tools/fdt-facts.py" "$dtb" --expect cpus=9 >/dev/null 2>&1; then
	echo "fdt-facts-test: FAIL -- an expectation the tree does not meet was accepted"
	exit 1
fi
echo "fdt-facts-test: the reader gives the POCO X5 Pro's timer, cores and GIC, and refuses a wrong expectation"
