#!/bin/bash
# Make ../Mu-Silicium ready for the davinci port: a clone at a pinned commit, with this directory's
# port (mu-silicium.patch and files/) put into it. Nothing of raphael's port goes in.
#
#   devices/davinci/uefi/apply.sh [COMMIT]
#
# The commit is either the argument, this directory's BASE file, or MU_SILICIUM_BASE. See README.md
# here for what has to exist in this directory before it can run, and for the two changes the patch
# carries.
set -e
cd "$(dirname "$(readlink -f "$0")")"
MU=../../../Mu-Silicium
BASE=${1:-${MU_SILICIUM_BASE:-$(cat BASE 2>/dev/null || true)}}
[ -n "$BASE" ] || { echo "uefi/apply.sh: pin a Mu-Silicium commit: apply.sh COMMIT, or write it to BASE" >&2; exit 2; }
[ -d files/Platforms ] && [ -s mu-silicium.patch ] ||
    { echo "uefi/apply.sh: no davinci port here yet (need files/Platforms/<vendor>davinciPkg and mu-silicium.patch); see README.md" >&2; exit 2; }
[ -e $MU ] && { echo "uefi/apply.sh: $MU already exists"; exit 1; }
git clone https://github.com/Project-Silicium/Mu-Silicium.git $MU
git -C $MU checkout -q "$BASE"
git -C $MU submodule update --init --recursive
git -C $MU apply --whitespace=nowarn "$PWD/mu-silicium.patch"
cp -r files/. $MU/
echo "uefi/apply.sh: done; next: devices/davinci/uefi/README.md"
