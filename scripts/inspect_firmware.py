#!/usr/bin/env python3
"""Reproduce every measurement quoted in docs/Z6_固件开发手册.md.

    python scripts/inspect_firmware.py <workspace>

<workspace> must contain:
    Z_6_0380.bin   the official Z6 C 3.80 package
    key.json       the three XOR tables, recovered by nikon-fw-key-tool

Nothing is written; the script only reads and prints.
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from z6fw import container                      # noqa: E402
from z6fw.platform import z6_380 as P           # noqa: E402


def entropy(v: np.ndarray) -> float:
    c = np.bincount(v, minlength=256).astype(np.float64)
    p = c[c > 0] / v.size
    return float(-(p * np.log2(p)).sum())


def main(argv) -> int:
    ws = Path(argv[1] if len(argv) > 1 else ".").resolve()
    image_path = ws / "Z_6_0380.bin"
    key_path = ws / "key.json"
    if not key_path.exists():
        # common local layout: nikon-fw-key-tool lives under _repo/
        alt = ws / "_repo" / "key.json"
        if alt.exists():
            key_path = alt
    for p in (image_path, key_path):
        if not p.exists():
            print("missing: %s" % p)
            print("see README: you must supply your own firmware and recovered key file")
            return 2

    raw = image_path.read_bytes()
    v = np.frombuffer(raw, dtype=np.uint8)
    print("== 1. package identity ==")
    print("  size      : %d (0x%X)" % (len(raw), len(raw)))
    print("  sha256    : %s" % container.sha256(raw))
    print("  entropy   : %.6f" % entropy(v))
    print("  header    : %s" % raw[:32].hex())
    print("  label@0x20: %r" % raw[0x20:0x40])

    parsed = container.load(image_path, key_path)
    print("\n== 2. container structure ==")
    problems = container.check_structure(parsed)
    print("  structure : %s" % ("clean" if not problems else problems))
    count, dirsize = struct.unpack_from(">II", parsed.body, 0x20)
    print("  modules   : %d, directory %d bytes (48+32*%d = %d)"
          % (count, dirsize, count, 48 + 32 * count))
    for m in parsed.modules:
        print("    %-20s off=0x%08X len=%9d  crc=%s"
              % (m.name, m.offset, m.length, "ok" if container.crc_ok(m.data) else "BAD"))

    eg = parsed.module(P.MODULE_NAME).data
    print("\n== 3. EG module and load base ==")
    print("  size      : %d (0x%X)" % (len(eg), len(eg)))
    print("  sha256    : %s" % container.sha256(eg))
    print("  crc residu: 0x%04X" % container.crc16(eg))
    print("  version   : %r" % eg[0x20:0x2C])
    scatter = struct.unpack_from("<4I", eg, 0x14000)
    print("  scatter   : (0x%08X, 0x%08X, 0x%08X, 0x%08X)" % scatter)
    ok = scatter[3] == P.BASE + 0x6C
    print("  base check: word[3] == 0x%08X -> %s"
          % (P.BASE + 0x6C, "BASE = 0x%08X confirmed" % P.BASE if ok else "MISMATCH"))

    print("\n== 4. JPEG output size table (0x%08X, stride 6) ==" % P.SIZE_TABLE)
    off = P.SIZE_TABLE - P.BASE
    for i in range(14):
        w, h, aid = struct.unpack_from("<3H", eg, off + i * 6)
        if not (1000 <= w <= 6048 and 500 <= h <= 4024):
            break
        print("    [%2d] %4dx%-4d aspect_id=%d" % (i, w, h, aid))

    print("\n== 5. source module names embedded in EG ==")
    pat = re.compile(rb"[A-Za-z_][A-Za-z0-9_./\\-]{1,60}\.(?:c|cpp|cc|h|hpp|s|inc|asm)\Z")
    names, i, n = set(), 0, len(eg)
    while i < n:
        if 0x20 <= eg[i] < 0x7F:
            j = i
            while j < n and 0x20 <= eg[j] < 0x7F:
                j += 1
            if pat.match(eg[i:j]):
                names.add(eg[i:j].decode("latin-1").split("/")[-1].split("\\")[-1])
            i = j
        else:
            i += 1
    print("  distinct module names: %d" % len(names))
    for k in sorted(names, key=str.lower)[:25]:
        print("    %s" % k)
    print("    ... (use docs/Z6_固件开发手册.md section 6 for the grouped list)")

    print("\n== 6. presets ==")
    from z6fw.features import aspect
    for name in aspect.PRESETS:
        d = aspect.describe(name)
        print("  %-14s %s" % (name, d["note"]))
        for q, s in d["sizes"].items():
            print("      %s %4dx%-4d edge32=%s" % (q, s["width"], s["height"], s["edge32"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
