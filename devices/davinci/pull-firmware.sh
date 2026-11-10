#!/bin/bash
# Pull davinci's own firmware out of its Android into the fw-*/ directories at the top of the
# repository (never committed: it is the vendor's). The phone is on adb, in Android.
#
# The names differ from the POCO's and from raphael's, so each group is asked off the phone rather
# than assumed: `adb shell ls` with a pattern, and whatever it names is pulled. A group that finds
# nothing says so -- that is a fact about this ROM, not an error.
set -e
cd "$(dirname "$0")/../.."
pull() { # DIR FILES...  (missing files are told, not fatal)
	local dir=$1; shift
	mkdir -p "$dir"
	local n=0
	for f in "$@"; do adb pull "$f" "$dir/" >/dev/null 2>&1 && n=$((n + 1)); done
	[ "$n" -gt 0 ] || echo "pull-firmware.sh: $dir: nothing on this ROM matched"
	echo "pull-firmware.sh: $dir: $n files"
}
onphone() { adb shell ls "$@" 2>/dev/null | tr -d '\r'; }

adb get-state >/dev/null
# The GPU: Adreno 618's a6xx family. davinci's GPU is not raphael's A640, so its files are not
# either; whatever this ROM ships under /vendor/firmware is what hakios.adreno.c will need.
pull fw-gpu $(onphone /vendor/firmware/a6*.bin /vendor/firmware/a6*_sqe.fw /vendor/firmware/a6*_zap.*)
# Wi-Fi: WCN3990 behind ICNSS, as on raphael: the firmware that MPSS serves over TFTP, and the
# board-data file (cnss-daemon picks it; this phone's build may name it differently from raphael's).
pull fw-wifi $(onphone /vendor/firmware_mnt/image/wlanmdsp.mbn /vendor/firmware/bd*.bin /vendor/etc/wifi/bd*.bin)
# The audio DSP: the same image's adsp.mdt and its segments.
pull fw-audio $(onphone /vendor/firmware_mnt/image/adsp.mdt /vendor/firmware_mnt/image/adsp.b*)
# The modem: its image, and the whole image directory for the TFTP side (IPA, wlanmdsp, ...).
pull fw-modem $(onphone /vendor/firmware_mnt/image/modem*)
mkdir -p fw-modem/image && adb pull /vendor/firmware_mnt/image fw-modem/ >/dev/null 2>&1 &&
	echo "pull-firmware.sh: fw-modem/image: the modem's own files (TFTP)"
echo "pull-firmware.sh: done; Wi-Fi also wants fw-wifi/mac (the radio's address) and fw-wifi/network (the network's name and passphrase)"
