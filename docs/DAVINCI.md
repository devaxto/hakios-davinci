# Porting HakiOS to davinci (Redmi K20 / Mi 9T, SM7150)

The phone is a Redmi K20 / Mi 9T: Snapdragon 730 (SM7150), Adreno 618, the same 1080×2340 AMOLED as
raphael, WCN3990 Wi-Fi behind ICNSS. It is the closest phone to raphael this repository has, which is
why it is the second port after it — but "closest" means the parts *between* the SoCs carry over,
not the SoCs themselves.

## Where the port stands

| Done | Where |
|---|---|
| the device directory | [devices/davinci/](../devices/davinci/) |
| the kernel knows three boards, not "raphael or not" | `enum hakios_board` and `hakios_board()` in `bsd/sys/hakios.input.h`, `bsd/dev/hakios.input.c` |
| the loader knows the phone by name, not by its framebuffer address | `platform_davinci` and `platform=<name>` in [xnuloader/loader.c](../xnuloader/loader.c) |
| DTB builder, per-device UEFI extraction, `soc.args` | [tools/build-davinci-dtb.py](../tools/build-davinci-dtb.py), [tools/extract-uefi.py](../tools/extract-uefi.py), [devices/davinci/pull-soc.sh](../devices/davinci/pull-soc.sh) |
| the phone's own numbers, read out of its tree | [tools/fdt-facts.py](../tools/fdt-facts.py): the timer's interrupt, the cores, the GIC, the panel, the touch, storage, the GPU, the PMICs |

Nothing of *this* tree has run on a davinci yet. The order below is the order to find that out in.

## What the phone's own tree says

An earlier davinci project on this machine (see the last section) holds this phone's boot DTB. Read
with [tools/fdt-facts.py](../tools/fdt-facts.py) and [tools/soc-args.py](../tools/soc-args.py), it
answers most of what the port was waiting for. Every value below is *read out of the phone's tree*;
where it agrees with raphael, the agreement is a finding, not an assumption.

| Fact | Value | Where it goes |
|---|---|---|
| model / compatible | SDMMAGPIE SoC, `qcom,sdmmagpie`, msm-id `0x16d` | the SoC is not SM8150 |
| cores | 8 in one cluster: 6 × A55 (capacity 1024, cores 0-5) + 2 × A76 (1740, cores 6-7), `reg = core << 8` | `platform_davinci`: `.cores`, `.core_shift`, `.small_cores = 0x3f` |
| GIC | distributor `0x17a00000`+0x10000, redistributors `0x17a60000`+0x100000 | same as raphael |
| timer | PPIs 1/2/3/0; the third (virtual) is **PPI 3 → `gic_timer_irq=19`** | `device.conf` BOOTARGS: raphael's 19, not redwood's 27 |
| UFS | `ufshc@1d84000` (`ufs_mem` +0x3000, ICE `0x1d90000`) | **the same controller base as raphael** |
| GPU | `kgsl-3d0@5000000`, chipid `0x6010800`, 11 power levels 180–825 MHz | `hakios.adreno.c`'s A618 branch |
| PMICs | PM6150 + PM6150L + PM8009 on SPMI `0xc440000`; PON: power, volume down | `hakios.buttons.c` |
| Wi-Fi | `qcom,icnss@18800000`: +0x800000 of registers, SMMU iova `0xa0000000`, IPA iova `0xb0000000`, **stream `0x240`** | `hakios.wifi.c` |
| splash | `cont_splash_region@9c000000` +0x1700000 | `FB_BASE`: **the same address as raphael's**, which is why the loader needs `platform=davinci` |
| display | MDP `0xae00000`; the display has its own RSC at `0xaf20000` | `hakios.display.c` |
| SoC addresses | IPA `0x1e40000` / GSI `0x1e04000`, apps SMMU `0x15000000`, RSC `0x18220000`, cmd-db `0xc3f000c`, mpss `0x8b000000`, IPA firmware `0x97f10000`, smem `0x86000000`, imem `0x14600000`, IPA streams `0x520`/`0x522` | [devices/davinci/soc.args](../devices/davinci/soc.args) |

Three things this tree does **not** have, which the modem and display sections below depend on:

- **no `qcom,ipcc` node**: the inter-processor channel is the APCS GLink (`mailbox@17c00000`), so
  `soc_ipcc` keeps the kernel's raphael default and has to be *found* before the modem path is trusted;
- **no AOSS mailbox node** (`qcom,*aoss-qmp`): `soc_aoss` is equally unmeasured;
- **no panel and no touch node**: this is the boot DTB; the panel and the touch controller arrive
  through the `dtbo` overlays, so only the live tree (`/sys/firmware/fdt`, the file `pull-soc.sh`
  pulls) carries them.

That DTB is also where a `davinci` image gets its tree from, until `tools/build-davinci-dtb.py`
builds one out of the SM7150 kernel sources: at `out/davinci/davinci.dtb`, the path `device.conf`
already names.

## What carries over, and what does not

| Block | raphael (SM8150) | davinci (SM7150) | What it means here |
|---|---|---|---|
| Wi-Fi chain | WCN3990 + ICNSS + ath10k + MPSS/PAS | **same family** | `hakios.wifi.c`, `hakios.lx.c`, `hakios.wlfw.c` and the `check-wifi-*.py` hosts are reusable; the addresses, SIDs, CE SPI numbers, `wlanmdsp.mbn` and the BDF file are not |
| CPU frequency | OSM (SM8150's own block) | **EPSS**, as on redwood | take the EPSS path in `hakios.cpufreq.c`; its base and its firmware LUT come from davinci's tree |
| Panel | 1080×2340 AMOLED, DSI command mode | 1080×2340 AMOLED, DSI command mode | geometry and the TE-based `fb_scan=1` model survive; MDSS/dispcc offsets and panel timings do not |
| Boot chain | Mu-Silicium `raphaelPkg` | its own `davinciPkg` | see [devices/davinci/uefi/](../devices/davinci/uefi/): nothing of raphael's memory map or firmware patches applies |
| GPU | Adreno 640, gpucc at `0x02c90000` | Adreno 618 | new gpucc/GMU map, its own zap shader and firmware; `hakios.adreno.c` needs an A618 branch beside the A640 and A642L ones |
| PMIC | PM8150/PM8150L | PM6150 + PM6150L + PM8009 | PON block and GPIO numbers for the keys in `hakios.buttons.c`, and the rails the Wi-Fi path switches |
| Storage | UFS HC at `0x01d84000`, raphael's own userdata | the same UFS HC at `0x01d84000`, its own partitions | the *controller code* carries over untouched; the store's identity does not (see "Storage" below) |

## The order of work

### 1. UEFI

The gate everything else waits behind: without a Mu-Silicium build for this phone there is no loader,
no `./xl`, no log. [devices/davinci/uefi/README.md](../devices/davinci/uefi/README.md) lists what has
to exist in that directory; the modules come out of davinci's own XBL with
`tools/extract-uefi.py --device davinci`.

Two things come out of this step and go straight into the device directory:

- `FD_BASE` and `FD_SIZE` — where the shim puts the UEFI image, from the port's memory map;
- the framebuffer address — the loader prints it (`display 1080 x 2340 at ...`) and the *next*
  bring-up could then let the loader guess this phone, as it guesses raphael's.

### 2. Device tree

```sh
devices/davinci/pull-soc.sh                 # -> soc.args, fdt.local, and the facts below
tools/build-davinci-dtb.py ~/kernel/davinci # -> out/davinci/davinci.dtb and .facts
```

`pull-soc.sh` is worth running before anything is built: it reads the phone's own tree and prints
what every unknown in [../devices/davinci/device.conf](../devices/davinci/device.conf) is waiting
for -- the timer's interrupt, the eight cores and which six are the slow ones, the two GIC regions,
the panel's geometry and mode, the touch controller and its firmware file, the UFS and GPU bases,
the PMICs. It writes nothing but `soc.args` and `fdt.local`, and copies no part of the tree.

The `.facts` file is the point: it prints the model, the board id, the eight cores, the two GIC
regions, the timer's virtual PPI (**`gic_timer_irq` = 16 + PPI**, the classic silent breakage) and the
touch controller's `compatible`. `gic_timer_irq` goes into `device.conf`'s `BOOTARGS`.

### 3. Loader

`platform_davinci` in `xnuloader/loader.c` is filled in with what SM7150 certainly shares (GIC,
peripheral window, core numbering: shift 8) and what it plainly does not (six A55s and two A76s, so
`small_cores = 0x3f`, not raphael's `0x0f`). The table above confirms all of it, `.small_cores`
included; `io_base`/`io_size` show up wrong at once as a kernel that faults on its first register.

### 4. Display, then the GPU

The first milestone is the kernel's own text on the panel with `display=...`/`fb_scan=0`: that only
needs the loader's framebuffer, not the MDSS driver. Then:

- `hakios.display.c` — `fb_scan=1`'s TE phase read is raphael's `hakios_is_raphael()` branch; davinci
  needs its own tear-check registers, or `fb_scan=0` until they are measured.
- `hakios.adreno.c` — Adreno 618: gpucc/GMU bases, the power levels in its DT, the zap shader and the
  `a6xx` firmware names from `/vendor/firmware`. The code already carries two generations
  (`a640`, and redwood's A642L), so the shape of the branch is there.

### 5. CPU frequency

Take the EPSS path (redwood's) rather than the OSM one: EPSS register base and the firmware's LUT
rows are read from davinci's tree (`soc_cpufreq`-style arguments or the DT nodes), not copied.

### 6. Storage

Read-only first (`ufs=2`, `ufs_write=0`), because two separate things are raphael's:

- the controller's base and clock/power map (from the DT);
- the **store's identity** — `hakios.ufs.c` refuses writes unless the partition matches raphael's
  userdata GUID, LBA and size (`507904`, `29136891` blocks), and `xnuloader/loader.c` does the same
  check on its side. Write constants for davinci only after reading its GPT and boot sectors on this
  phone, as `tools/ufs-survey.py` and `tools/ufs-read.py` do for raphael; they never write.

The bootloader already answers part of it without touching the store: `fastboot getvar all` on this
phone reports `product: davinci`, no A/B slot, and `userdata` of `0xCE45FB000` bytes (13,518,331
blocks of 4K) formatted `f2fs`, plus its whole partition list with sizes. That is where the size half
of the guard comes from; the LBA and the GUID still need the GPT. The dump is in
`logs/fastboot-vars.txt`, which is not in git.

### 7. Wi-Fi, modem, ADSP, camera

Last, and the largest code that *is* reusable. `hakios.wifi.c`'s raphael branch — APCS doorbell,
ICNSS/MPSS control, MSA and SMMU setup, RMTFS/TFTP/PD/PDR/QRTR — is the closer of the two to SM7150;
what changes is every address (`soc.args` carries IPA, GSI, IPCC/APCS, AOSS, RSC, SMMU, SMEM,
cmd-db, mpss region), the SIDs, the CE interrupt base and whether they are level or edge, plus
`wlanmdsp.mbn` and the BDF file this phone's cnss-daemon picks.

## The 40 places that ask "is this raphael?"

All `hakios_is_raphael()` call sites across `xnu/files/bsd/dev/` now have explicit `hakios_is_davinci()`
or shared `is_icnss()` branches so `davinci` never falls back to `redwood`'s SM7325 hardware addresses:

| File | Branch | On davinci (SM7150) |
|---|---|---|
| `bsd/dev/hakios.input.c` | touch controller dispatch | calls `raphael_touch_init()` for `hakios_is_raphael() \|\| hakios_is_davinci()` |
| `bsd/dev/raphael_touch.c` | GT9886 Normandy I2C (`0x5d`) | QUPv3 SE7 (`0x00a84000`), GCC wrapper 1 (`0x5200c`, RCG `0x18148`, branches `0x18004..0x18144`), NORTH TLMM (`0x03900000`) GPIOs 6/7 (I2C mux 1), 8 (reset), 9 (IRQ), PM6150L `ldoc6` 3000 mV via RPMh (`0x0c3f000c` cmd-db locator); never touches GPIO 90 |
| `bsd/dev/hakios.buttons.c` | PMIC SPMI PON + Volume Up GPIO | PM6150 PON gen2 (`0x008`, subtype `0x04`, masks `0x01`/`0x02`) + PM6150L GPIO2 (`0x4c1`) |
| `bsd/dev/hakios.cpufreq.c` | OSM frequency scaling | 2-domain SM7150 OSM (`0x18323000` for 6×A55 cores 0..5, `0x18325800` for 2×A76 cores 6..7) |
| `bsd/dev/hakios.lx.c` | ICNSS CE SPIs | SPIs `414..425` → GIC `446..457`, level-high (`is_icnss()`) |
| `bsd/dev/hakios.apple80211.c` | card name & WPA3/PMF bits | `"davinci: ath10k for the WCN3990"`, WPA3/PMF enabled (`hakios_is_raphael() \|\| hakios_is_davinci()`) |
| `bsd/dev/hakios.wifi.c` | MPSS + ICNSS + WCN3990 | `cmd-db` via `0x0c3f000c` locator, APCS `0x17c0000c`, `RADIO_STREAM = 0x240`, `WPSS_MEMORY = 0x8b000000` (`0x08400000`), `ICNSS_MSA_PHYS = 0x97d00000` (`0x180000`), 4 ICNSS rails (`ldoa9`, `ldoc1`, `ldoc2`, `ldoc10`) |
| `bsd/dev/hakios.adreno.c` | SDE scanout & Adreno 618 | 2-buffer TE page-flip (`0x9c000000`, `0x9ca00000` within 23 MiB `cont_splash_region`), VIG0/DMA0 auto-detect, Adreno 618 (`0x05000000`) guarded |
| `bsd/dev/hakios.display.c` | `fb_scan=1` command-mode TE | enabled for `hakios_is_raphael() \|\| hakios_is_davinci()` |
| `bsd/dev/hakios.ufs.c` | `ufs_write=1` partition guard | explicitly refused on `davinci` until GPT and `userdata` bounds are surveyed |

## What to measure on the phone

Most of the list below is one command while the phone is in Android with adb:
`devices/davinci/pull-soc.sh`. What it cannot answer is the bootloader's own memory map and the
framebuffer the firmware hands over, and those two only exist once a UEFI runs.

- [ ] UEFI DEBUG screen: the firmware's memory map → `FD_BASE`, `FD_SIZE`
- [ ] loader log: `display 1080 x 2340 at ...` → the framebuffer address; `platform davinci`
- [x] `pull-soc.sh`: `gic_timer_irq` 19, 8 cores and `small_cores` `0x3f`, GIC, board id, UFS, GPU, PMICs
- [x] `pull-soc.sh`: `soc.args` -- all of it except `soc_ipcc` and `soc_aoss`, which this tree has no
      node for ([devices/davinci/soc.args](../devices/davinci/soc.args))
- [ ] `pull-soc.sh` on the live phone: the panel's geometry and mode, the touch controller (neither is
      in the boot DTB: they come from the `dtbo` overlays)
- [ ] `userdata`'s GUID, LBA and size, read-only (`tools/ufs-read.py`, `tools/ufs-survey.py`)
- [ ] Wi-Fi: `wlanmdsp.mbn`, the BDF file cnss-daemon picks, `qcom,pas-id`, the SMMU SID

## Rules this port keeps

- Vendor firmware, the DTBs and Apple's files stay out of git (see `COMPLIANCE.md`).
- Nothing of raphael's is copied into davinci's directory: not `FD_*`, not the XBL firmware patches,
  not the userdata constants, not the GPU firmware.
- `ufs_write=1` only after the store's identity has been re-read on this phone.
- A driver branch that is raphael's must be *decided* for davinci, not inherited from redwood.

`docs/PORTING.md` is the general guide for a new phone (its `common/` paths predate the move to
`devices/<name>/`); this file is davinci's instance of it.

## The earlier davinci project

On this machine, outside this repository, is an earlier attempt at the same phone: a fork of
`ios-sweet` (the Redmi Note 10 Pro, SM7150, port) renamed for davinci. Its architecture is not this
one — a C shim instead of UEFI, `fastboot boot` straight into a patched XNU (xnu-8796, ~69 patches
built on GitHub's macOS runners), the iPhone X 16.7.16 userland, HFS+ root in `userdata` — and none of
its code is taken here. What it is worth is what it *proved* and what it *measured*:

1. **SM7150 runs this class of kernel on this phone.** By its own log the phone boots XNU and reaches
   the iOS home screen (touch, buttons, a writable HFS+ root); the eight cores enumerate exactly as
   the table above says. The SoC is not the obstacle.
2. **The numbers in that table.** Its `dtb/` holds this phone's boot DTB, its device-tree generator
   (`tools/mkadt.py`) carries the Apple-device-tree constants it had to work out — GIC, virtual timer
   INTID 19, splash `0x9c000000`, UFS, Adreno 618, the A55/A76 split at cores 0-5 / 6-7 — and its
   `NOTES.md` is 230 KB of what went wrong on the way there.
3. **Its breakage is not inherited.** What it reports as broken — a pink line, half the screen black,
   white squares — is its own frame-copy path writing through the DPU, not something
   `hakios.display.c` shares. Likewise its dead touch (`davinci_touch_probeonly`) and its slow boot
   are its shim's, not this boot chain's.

What does not carry over: its XNU patch series, its shim, its boot-args and its device-tree builder.
This port's kernel is raphael's XNU source, its boot chain is Mu-Silicium UEFI plus `XNULOADER`, and
its device tree is davinci's own.
