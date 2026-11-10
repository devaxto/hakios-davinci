#!/usr/bin/env python3
"""Extract raphael's XBL -- tools/extract-uefi.py --device raphael, under the name it has always had.

The image is checked against devices/raphael/uefi/xbl.sha256, and the byte-checked firmware fixes
are devices/raphael/uefi/raphael-firmware-patches.json. Arguments are passed through.
"""
import os
import sys

tools = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable,
         [sys.executable, os.path.join(tools, 'extract-uefi.py'), '--device', 'raphael'] + sys.argv[1:])
