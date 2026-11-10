#!/bin/bash
# Build the davinci port against the shared baseline; no flashing or image deployment.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
source devices/davinci/device.conf
export PLATFORM UEFI_TARGET UEFI_FD DTB PAYLOAD_BASE
# device.conf carries both; the shim and mkxnuimg.py take them from the environment.
if [ -n "${FD_BASE:-}" ] && [ -n "${FD_SIZE:-}" ]; then
    export FD_BASE FD_SIZE
fi
case ${1:-kernel} in
kernel)
    python3 tools/mk-ath10k.py
    WIFI_OBJECT="$ROOT/xnu-deps/build/ath10k/out/ath10k.o" ./xnu-build.sh -j"${JOBS:-8}"
    ;;
loader) ./xnuloader/build.sh ;;
images)
    GL=1 REST=1 QUIET=1 OSLOG= RC="$ROOT/userland/rc.launchd" \
    RC_JOBS="$ROOT/devices/davinci/davinci.jobs" userland/build.sh
    ;;
boot)
    mkdir -p out/davinci
    python3 xnuloader/mkpayload.py -o out/davinci/usb-payload.bin loader.efi=xnuloader/loader.efi --usb
    python3 mkxnuimg.py -p out/davinci/usb-payload.bin -o out/davinci/boot.img
    ;;
run) ./xl run ;;
*) echo "usage: $0 {kernel|loader|images|boot|run}" >&2; exit 2 ;;
esac
