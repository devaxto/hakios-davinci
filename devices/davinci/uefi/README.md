# davinci UEFI

Mu-Silicium, pinned to the commit in `BASE`, with a `davinciPkg` platform package of its own. Nothing
of `devices/raphael/uefi/` is reused except the shape: its module list, its memory map and its
firmware patches belong to raphael's own XBL.

## What is in this directory

| Path | Where it comes from |
|---|---|
| `BASE` | `635acc9c92ee8a35db8565b136cc36ddc2026db5` (pinned `sm7150-davinci` tree with working submodule SHAs) |
| `files/Platforms/Xiaomi/davinciPkg/` | davinci's own platform package: module lists (`Include/*.inc`), memory map (`.dsc`, `.fdf`, `DeviceMemoryMapLib.c`) and `XNU_PAYLOAD_BOOT` + `XNU_NO_DISK_LOG` build flags |
| `files/Resources/Configs/davinci.conf` | davinci's BootShim and FD configuration (`TARGET_FD_BASE=0x9FC00000`, `TARGET_FD_SIZE=0x00300000`, `TARGET_FD_BLOCKS=0x300`) |
| `files/Resources/Scripts/davinci.sh` | Android boot image packaging script for `DAVINCI_UEFI.fd` |
| `files/Silicon/Silicium/SiliciumPkg/Library/PlatformBootManagerLib/XnuLoader.[ch]` | RAM payload (`XNUP` at `0xF0000000`) loader hook |
| `mu-silicium.patch` | `BootShim/BootShim.S` + `BootShim/Makefile` (`XNUP` payload copy to `PAYLOAD_BASE`) and `PlatformBootManagerLib` (`XnuLoaderMain()` call in `PlatformBootManagerAfterConsole()`) |
| `export.sh` | refreshes `BASE`, `mu-silicium.patch`, and `files/` from `Mu-Silicium/` or `out/uefi-src/` without exporting proprietary binaries or DTBs |

The UEFI modules themselves (`Binaries/davinci`) are extracted from the phone, never copied:

```sh
# 1. the XBL off the phone (read-only; tools/ufs-read.py does it over the loader's own storage code)
# 2. extract the AArch64 modules and pin the image's SHA-256
tools/extract-uefi.py --device davinci --xbl out/davinci/firmware/xbl.img
```

The extraction refuses a second run at a different XBL until the SHA-256 in the command below is
updated, because the firmware patches are checked against that exact build:

```sh
tools/extract-uefi.py --device davinci --xbl out/davinci/firmware/xbl.img \
    --expect-sha256 <sha256 of this xbl.img>
```

## Build

```sh
devices/davinci/uefi/apply.sh <mu-silicium commit>
# dependencies and the Python environment: as Mu-Silicium's own README says
cd Mu-Silicium
python3 build_uefi.py -d davinci -r DEBUG
```

The DEBUG build is the one to bring up with: it prints the firmware's memory map on the panel, and
that is where `FD_BASE`, `FD_SIZE` and the framebuffer address in
[../device.conf](../device.conf) come from.

## The memory map and the file it comes out as

`FD_BASE=0x9FC00000`, `FD_SIZE=0x00300000` are already in [../device.conf](../device.conf): they
are what davinci's own Mu-Silicium port builds with (`Resources/Configs/davinci.conf` there:
`TARGET_FD_BASE`, `TARGET_FD_SIZE`, `TARGET_FD_BLOCKS=0x300`; block size `0x1000` in
`Platforms/Xiaomi/davinciPkg/davinci.fdf`). They happen to be raphael's numbers too -- the window
XBL leaves free for the firmware is the same on these SoCs -- so the port takes them from davinci's
build, not from raphael's file.

That build writes `Build/davinciPkg/<mode>_CLANGPDB/FV/DAVINCI_UEFI.fd`: named after the platform,
not `SILICIUM_UEFI.fd`, which is what `mkxnuimg.py` looks for under a `Mu-Silicium/` tree. Point
`UEFI_FD=` at it, and keep it exactly `FD_SIZE` long or the packer refuses it.

## What the FD comes from today

There is no `davinciPkg` and no `mu-silicium.patch` in this tree yet. The `DAVINCI_UEFI.fd` the
chain needs is built by the SM7150 fork below, and only its output is used:

| | |
|---|---|
| fork | `devaxto/mu-silicium-davinci-sm7150` (a fork of the reference one) |
| branch | `sm7150-davinci`, at `635acc9c` |
| what that commit is | HEAD's tree with the seven submodules pinned back to the SHAs of `12088f9`, the last commit whose davinci build succeeded |
| why the pin | with the newer `Mu_Tiano_Plus`, `EmbeddedPkg` no longer carries `Library/RealTimeClockLib.h`, which `SiliciumPkg/Library/RealTimeClockLibNull` includes: the platform stops compiling 11 s in |
| how it builds | Actions -> `davinci.yml` (workflow_dispatch): `build_uefi.sh -d davinci -r DEBUG`, artifact `uefi-images` = `Mu-davinci.img` |
| what comes out | `Mu-davinci.img` = `gzip(BootShim.bin + DAVINCI_UEFI.fd)` + the DTB; the shim is 144 bytes and the FD exactly `0x300000`, the `FD_SIZE` in [../device.conf](../device.conf) |

What that build does **not** have is the XNUP hook, which is this repository's own work: the fork's
UEFI has no reason to start a loader out of `PAYLOAD_BASE`. The hook point is
`PlatformBootManagerAfterConsole()` in `Silicon/Silicium/SiliciumPkg/Library/PlatformBootManagerLib`
(raphael's patch used the same function, in the older `BootManagerLib`), and `BootShim/BootShim.S`
needs the same `XNUP` copy block its raphael counterpart has — after `_CopyLoop`, where its `x4`
points one past the FD, before `ldr x5, _StackBase` reloads the entry address.

## Not to be carried over

- raphael's `Binaries/raphael`, and the prebuilt POCO files under `devices/poco-x5-pro/prebuilt/`.
- raphael's firmware patch offsets: they are byte offsets into *its* XBL build and are checked
  against its SHA-256.
- raphael's `BootManagerLib` and `Sec.c` hunks: they are written against the Mu-Silicium commit in
  `BASE`. A newer tree (the SM7150 fork below) has `PlatformBootManagerLib` and the `XenonGUI`
  application instead, so the XNUP hook is a port to that shape, not a `git apply`.

Reference: an existing, unrelated Mu-Silicium fork for this phone
(`hiratazx-playground/mu-silicium-davinci-sm7150`, branch `sm7150-davinci`) carries a `davinciPkg`
and builds `Mu-davinci.img` in CI -- that is where the two numbers above and the `.fd` name come
from. Its patches are made against its own Mu-Silicium commit and are not this repository's.
