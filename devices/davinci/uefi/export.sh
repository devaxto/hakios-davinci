#!/bin/bash
# Export only davinci source changes; proprietary firmware and DTBs remain local.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
MU=${MU_SILICIUM:-../../../Mu-Silicium}
[ -d "$MU" ] || MU=../../../out/uefi-src
git -C "$MU" rev-parse HEAD~1 > BASE
git -C "$MU" diff HEAD~1..HEAD -- BootShim Silicon/Silicium/SiliciumPkg/Library/PlatformBootManagerLib/PlatformBootManagerLib.c Silicon/Silicium/SiliciumPkg/Library/PlatformBootManagerLib/PlatformBootManagerLib.inf > mu-silicium.patch
stage=$(mktemp -d files-export.XXXXXX)
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/Platforms/Xiaomi" "$stage/Resources/Configs" "$stage/Resources/Scripts"
cp -a "$MU/Platforms/Xiaomi/davinciPkg" "$stage/Platforms/Xiaomi/"
cp "$MU/Resources/Configs/davinci.conf" "$stage/Resources/Configs/"
cp "$MU/Resources/Scripts/davinci.sh" "$stage/Resources/Scripts/"
mkdir -p "$stage/Silicon/Silicium/SiliciumPkg/Library/PlatformBootManagerLib"
cp "$MU/Silicon/Silicium/SiliciumPkg/Library/PlatformBootManagerLib/"XnuLoader.[ch] "$stage/Silicon/Silicium/SiliciumPkg/Library/PlatformBootManagerLib/"
rm -rf files
mv "$stage" files
trap - EXIT
