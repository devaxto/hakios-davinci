# Redmi K20 / Mi 9T (davinci)

SM7150, Adreno 618, the same 1080×2340 AMOLED as raphael. iOS 16.5 20F66, GLES only, following
HakiOS main.

**The davinci UEFI chain and SM7150 kernel driver branches are wired.** What is done: the device
directory, the Mu-Silicium UEFI port (`devices/davinci/uefi/`), the loader's `platform_davinci`, the
kernel's board identity (`hakios_is_davinci()`), and this phone's own SM7150/PM6150/PM6150L driver
paths across touch (`raphael_touch.c`: GT9886 Normandy on QUPv3 SE7 `0x00a84000`, NORTH TLMM
`0x03900000` GPIOs 6/7/8/9, `ldoc6` 3000 mV via RPMh `0x0c3f000c` cmd-db locator, never touching
GPIO 90), buttons (`hakios.buttons.c`: PM6150 PON `0x008` + PM6150L GPIO2 `0x4c1`), CPU frequency
(`hakios.cpufreq.c`: 2-domain SM7150 OSM at `0x18323000` / `0x18325800` for 6×A55 + 2×A76), display
(`hakios.display.c`, `hakios.adreno.c`: 2-buffer TE page-flip inside the 23 MiB `0x9c000000` splash
region), Wi-Fi (`hakios.wifi.c`, `hakios.lx.c`, `hakios.apple80211.c`: WCN3990 + ICNSS stream `0x240`,
MPSS `0x8b000000`, MSA `0x97d00000`, `ldoa9`/`ldoc1`/`ldoc2`/`ldoc10`), and UFS write protection
(`hakios.ufs.c`). Details are in [docs/DAVINCI.md](../../docs/DAVINCI.md).

## Build

From the repository root, with the local toolchain, as for any port:

```sh
devices/davinci/build.sh kernel
devices/davinci/build.sh loader
GL=1 REST=1 QUIET=1 devices/davinci/build.sh images
```

`device.conf` carries the values that are known and comments the ones that are not. Three of them
come only from this phone:

| Value | Where it comes from | State |
|---|---|---|
| `FD_BASE`, `FD_SIZE` | davinci's own Mu-Silicium port builds with them (`Resources/Configs/davinci.conf`: `0x9FC00000`, `0x00300000`, 0x300 blocks of 0x1000); `./xl memmap` on the running loader confirms them | **set** |
| the framebuffer address | the device tree's `cont_splash_region`: `0x9c000000` (`FB_BASE`); the loader prints its own as `display 1080 x 2340 at ...` | expected, same address as raphael's |
| `gic_timer_irq` | the device tree's `arm,armv8-timer` interrupts: virtual PPI number + 16 | **measured: PPI 3, so 19** |

## Run

The phone's own firmware is not in the repository; pull it first, then the DTB, then the SoC args:

```sh
devices/davinci/pull-firmware.sh             # the vendor's files into fw-*/ at the top (never committed)
devices/davinci/pull-soc.sh                  # -> soc.args, fdt.local, and the facts the port needs
tools/build-davinci-dtb.py ~/kernel/davinci  # -> out/davinci/davinci.dtb (+ .dts, .facts)
```

`devices/davinci/soc.args` is already in the tree, generated from this phone's boot DTB, and
`out/davinci/davinci.dtb` can come from the same DTB instead of the SM7150 kernel sources (which
`build-davinci-dtb.py` needs); what neither of them carries is the panel and the touch controller,
which live in the `dtbo` overlays. That is what `pull-soc.sh`'s live tree (`/sys/firmware/fdt`) has
and the build-time one does not.

A run is the usual one; `platform=davinci` is appended from `PLATFORM` in `device.conf` by
`devices/davinci/build.sh run` and by `tools/modem-cycle.sh`:

```sh
devices/davinci/build.sh run                        # == PLATFORM=davinci ./xl run
PLATFORM=davinci tools/modem-cycle.sh "ufs=0 ufs_write=0" 300
```

Without `platform=davinci` the loader has nothing to recognise this phone by: its framebuffer is at
neither address the loader knows, so it treats the phone as QEMU's virt machine and the run stops at
the first register it touches.

The first boot is deliberately bare: cores, display, timer. Only then `touchscreen=1`, `cpufreq=1`,
`gpu=1`, `ufs=2`. Storage writes (`ufs_write=1`) stay off until the userdata identity has been
re-read on this phone: the constants in `hakios.ufs.c` are raphael's and are refused on any other.

## Where the work is

| What | Where |
|---|---|
| the port's plan, in order, with the known SM7150 differences | [docs/DAVINCI.md](../../docs/DAVINCI.md) |
| UEFI (Mu-Silicium `davinciPkg`) | [uefi/](uefi/) |
| the loader's description of the phone | `platform_davinci` in [xnuloader/loader.c](../../xnuloader/loader.c) |
| the kernel's notion of which phone it is | `hakios_board()` in [hakios.input.c](../../xnu/files/bsd/dev/hakios.input.c) |
| the device tree builder and the SoC args | [tools/build-davinci-dtb.py](../../tools/build-davinci-dtb.py), [pull-soc.sh](pull-soc.sh) |
