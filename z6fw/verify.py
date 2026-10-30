"""Post-patch verification for Z6 EG candidates.

Every check is static and offline. Passing them means the candidate is
self-consistent; it does not mean the camera will accept or behave correctly.
"""
from __future__ import annotations

import struct

from . import container
from .patch import crc16


def check_module(module: bytes, *, stock_sha256: str | None = None) -> list[str]:
    problems = []
    if len(module) < 4:
        problems.append("module is too short")
        return problems
    if crc16(module) != 0:
        problems.append("CRC residue is 0x%04X, expected 0" % crc16(module))
    if stock_sha256 is not None:
        got = container.sha256(module)
        if got == stock_sha256:
            problems.append("module is still identical to stock")
    ver = module[0x20:0x2C]
    if not ver.startswith(b"Ver."):
        problems.append("version string missing at module offset 0x20 (%r)" % ver)
    scatter = struct.unpack_from("<4I", module, 0x14000)
    if scatter[3] != 0x1002006C:
        problems.append("scatter descriptor trailer is 0x%08X, expected 0x1002006C"
                        % scatter[3])
    return problems


def check_size_table(module: bytes, expect: dict[str, tuple[int, int]]) -> list[str]:
    """Verify the 16:9 records read back as the requested sizes."""
    from .platform import z6_380 as P
    problems = []
    base = P.SIZE_TABLE - P.BASE
    for i, q in enumerate(("L", "M", "S")):
        off = base + (9 + i) * P.SIZE_RECORD
        w, h, aid = struct.unpack_from("<3H", module, off)
        want_w, want_h = expect[q]
        if (w, h) != (want_w, want_h):
            problems.append("16:9 %s reads %dx%d, expected %dx%d" % (q, w, h, want_w, want_h))
        if aid != 4:
            problems.append("16:9 %s aspect id is %d, expected 4" % (q, aid))
        if w % 4 or h % 4:
            problems.append("16:9 %s is not quantised to 4 pixels (%dx%d)" % (q, w, h))
        if not (0 < w <= 6048 and 0 < h <= 4024):
            problems.append("16:9 %s is outside the sensor (%dx%d)" % (q, w, h))
    return problems


def check_diff(stock: bytes, patched: bytes, expected_edits: int) -> list[str]:
    """Independent byte-level diff: only the declared fields may differ."""
    problems = []
    if len(stock) != len(patched):
        problems.append("length changed %d -> %d" % (len(stock), len(patched)))
        return problems
    diffs = [i for i in range(len(stock)) if stock[i] != patched[i]]
    # the trailing 2-byte CRC is expected to change as well
    payload_diffs = [i for i in diffs if i < len(stock) - 2]
    if len(payload_diffs) != expected_edits * 2:
        problems.append("payload differs in %d bytes, expected %d"
                        % (len(payload_diffs), expected_edits * 2))
    return problems
