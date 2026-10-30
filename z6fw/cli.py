"""Command line entry point for the Z6 firmware toolkit.

    python -m z6fw info
    python -m z6fw selftest
    python -m z6fw probe  --out build/EG162080-PROBE.BIN
    python -m z6fw aspect --preset aspect-21x9 --out build/EG162080-21x9.BIN
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import container, verify
from .features import aspect
from .patch import apply_patch, selftest as run_selftest
from .platform import z6_380 as P

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE = ROOT / "Z_6_0380.bin"
DEFAULT_KEY = ROOT / "key.json"
FALLBACK_KEY = ROOT / "_repo" / "key.json"
DEFAULT_OUT = ROOT / "build"


def load_stock_eg(image: Path, key: Path) -> tuple[bytes, dict]:
    if not key.exists() and FALLBACK_KEY.exists():
        key = FALLBACK_KEY
    parsed = container.load(image, key)
    problems = container.check_structure(parsed)
    if problems:
        raise SystemExit("stock container has problems:\n  " + "\n  ".join(problems))
    eg = parsed.module(P.MODULE_NAME).data
    return eg, {"modules": [{"name": m.name, "offset": hex(m.offset), "length": m.length}
                            for m in parsed.modules]}


def cmd_info(args) -> int:
    eg, meta = load_stock_eg(args.image, args.key)
    print("stock EG module")
    print("  name   : %s" % P.MODULE_NAME)
    print("  size   : %d (0x%X)" % (len(eg), len(eg)))
    print("  sha256 : %s" % container.sha256(eg))
    print("  crc    : residue 0x%04X" % container.crc16(eg))
    print("  base   : 0x%08X" % P.BASE)
    print("  modules in package:")
    for m in meta["modules"]:
        print("    %-20s off=%s len=%d" % (m["name"], m["offset"], m["length"]))
    print("  presets:")
    for name in aspect.PRESETS:
        d = aspect.describe(name)
        print("    %-14s %s" % (name, d["note"]))
        for q, s in d["sizes"].items():
            print("        %s %4dx%-4d edge32=%s" % (q, s["width"], s["height"], s["edge32"]))
    return 0


def cmd_selftest(args) -> int:
    eg, _ = load_stock_eg(args.image, args.key)
    result = run_selftest(eg)
    same = result.data == eg
    print("selftest: %s (%d bytes)" % ("identical" if same else "MISMATCH", len(result.data)))
    problems = verify.check_module(result.data)
    print("structure: %s" % ("clean" if not problems else problems))
    return 0 if same and not problems else 1


def _find_zero_run(data: bytes, minimum: int = 0x400) -> int:
    run_start, run_len = 0, 0
    for i, b in enumerate(data):
        if b == 0:
            if run_len == 0:
                run_start = i
            run_len += 1
            if run_len >= minimum:
                return run_start + run_len // 2
        else:
            run_len = 0
    raise SystemExit("no zero run of %d bytes found" % minimum)


def cmd_probe(args) -> int:
    eg, _ = load_stock_eg(args.image, args.key)
    at = _find_zero_run(eg)
    probe = bytearray(eg)
    probe[at] ^= 0xFF
    probe = bytes(probe)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(probe)
    print("probe written: %s" % out)
    print("  flipped byte at module offset 0x%X (was 0x00, now 0xFF)" % at)
    print("  CRC residue now 0x%04X  (stock was 0x0000)" % container.crc16(probe))
    print("  size unchanged: %d" % len(probe))
    print()
    print("Purpose: the camera's CRC check must run before any flash write, so a")
    print("corrupt file should be rejected without modifying the camera. The reply")
    print("tells us whether this model reads standalone EG files at all.")
    return 0


def cmd_aspect(args) -> int:
    eg, _ = load_stock_eg(args.image, args.key)
    info = aspect.describe(args.preset)
    edits = aspect.build_edits(args.preset)
    result = apply_patch(eg, edits, base=P.BASE, expected_sha256=P.STOCK_SHA256)
    problems = verify.check_module(result.data, stock_sha256=P.STOCK_SHA256)
    expect = {q: (s["width"], s["height"]) for q, s in info["sizes"].items()}
    problems += verify.check_size_table(result.data, expect)
    problems += verify.check_diff(eg, result.data, len(edits))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result.data)
    report = {"preset": info, "patch": result.report, "problems": problems}
    Path(str(out) + ".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2, ensure_ascii=False))
    print("edits:")
    for e in result.report["edits"]:
        print("  %-44s %s -> %s" % (e["name"], e["expected_hex"], e["replacement_hex"]))
    print("written: %s" % out)
    if not P.CROP_GEOMETRY_PATCHED:
        print()
        print("!! WARNING: crop geometry is not patched yet.")
        print("!! This candidate changes the output size table only, so the camera will")
        print("!! resample the stock 16:9 window into the new height - the image will be")
        print("!! squeezed, not cropped. Build and inspect only; do NOT flash.")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  - %s" % p)
        return 1
    print("verification: clean (structure only)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="z6fw", description=__doc__)
    ap.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    ap.add_argument("--key", type=Path, default=DEFAULT_KEY)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="show the stock EG module and available presets").set_defaults(func=cmd_info)
    sub.add_parser("selftest", help="repack with no edits; must be byte identical").set_defaults(func=cmd_selftest)

    p = sub.add_parser("probe", help="write a CRC-corrupt file for the channel test")
    p.add_argument("--out", default=str(DEFAULT_OUT / "EG162080-PROBE.BIN"))
    p.set_defaults(func=cmd_probe)

    a = sub.add_parser("aspect", help="build an aspect-ratio candidate")
    a.add_argument("--preset", required=True, choices=sorted(aspect.PRESETS))
    a.add_argument("--out")
    a.set_defaults(func=cmd_aspect)

    args = ap.parse_args(argv)
    if not args.image.exists():
        print("missing firmware package: %s" % args.image)
        print("Put the official Z_6_0380.bin in the repository root; it is gitignored.")
        print("This project ships no firmware.")
        return 2
    if not args.key.exists() and not FALLBACK_KEY.exists():
        print("missing key file: %s" % args.key)
        print("Recover the XOR tables with nikon-fw-key-tool and place key.json here;")
        print("this project ships no key material.")
        return 2
    if getattr(args, "out", None) is None and args.cmd == "aspect":
        args.out = str(DEFAULT_OUT / ("EG162080-%s.BIN" % args.preset.replace("aspect-", "")))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
