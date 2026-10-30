"""Checked equal-length edits and aligned code append with a fresh EG CRC.

Semantics mirror the reference implementation in `_repo/wonder-lantern-z30-main`:
every edit must be equal length and must match the expected stock bytes; appended
code goes before the trailing 2-byte CRC and must be four-byte aligned; the module
CRC is recomputed and re-verified before the result is returned.
"""
from __future__ import annotations

import binascii
from dataclasses import dataclass, field


def crc16(data: bytes) -> int:
    return binascii.crc_hqx(data, 0)


@dataclass(frozen=True)
class Edit:
    offset: int          # module-relative
    expected: bytes
    replacement: bytes
    name: str

    def __post_init__(self):
        if not self.expected:
            raise ValueError("edit %s has empty expected bytes" % self.name)
        if len(self.expected) != len(self.replacement):
            raise ValueError("edit %s is not equal length (%d -> %d)"
                             % (self.name, len(self.expected), len(self.replacement)))


@dataclass
class PatchResult:
    data: bytes
    report: dict = field(default_factory=dict)


def apply_patch(source: bytes, edits, append: bytes = b"", *,
                base: int, expected_sha256: str | None = None,
                capacity: int | None = None) -> PatchResult:
    from .container import sha256

    source = bytes(source)
    append = bytes(append)

    if len(source) < 4 or crc16(source) != 0:
        raise ValueError("source is not a valid EG module (CRC residue 0x%04X)" % crc16(source))
    if expected_sha256 is not None:
        got = sha256(source)
        if got != expected_sha256:
            raise ValueError("source SHA-256 mismatch\n  expected %s\n  actual   %s"
                             % (expected_sha256, got))

    start = len(source) - 2                     # payload ends before the CRC
    if append:
        if start % 4 or len(append) % 4:
            raise ValueError("appended code must be four-byte aligned")
        if capacity is not None and start + len(append) > capacity:
            raise ValueError("payload would exceed region capacity "
                             "(%d + %d > %d)" % (start, len(append), capacity))

    ordered = sorted(edits, key=lambda e: e.offset)
    end = 0
    for e in ordered:
        if e.offset < end:
            raise ValueError("edit %s overlaps the previous edit" % e.name)
        if e.offset + len(e.expected) > start:
            raise ValueError("edit %s crosses the payload boundary" % e.name)
        actual = source[e.offset:e.offset + len(e.expected)]
        if actual != e.expected:
            raise ValueError("edit %s: expected bytes mismatch at 0x%X\n"
                             "  expected %s\n  actual   %s"
                             % (e.name, e.offset, e.expected.hex(), actual.hex()))
        end = e.offset + len(e.expected)

    out = bytearray(source[:-2] + append)
    for e in ordered:
        out[e.offset:e.offset + len(e.replacement)] = e.replacement
    out += crc16(bytes(out)).to_bytes(2, "big")
    result = bytes(out)
    if crc16(result) != 0:
        raise ValueError("output CRC self-check failed")

    report = {
        "source_size": len(source),
        "source_sha256": sha256(source),
        "size": len(result),
        "sha256": sha256(result),
        "crc_residue": 0,
        "base": hex(base),
        "append_address": hex(base + start),
        "append_length": len(append),
        "offset_space": "decoded_eg_module",
        "edits": [{"name": e.name,
                   "offset": hex(e.offset),
                   "address": hex(base + e.offset),
                   "size": len(e.expected),
                   "expected_hex": e.expected.hex(),
                   "replacement_hex": e.replacement.hex()} for e in ordered],
    }
    return PatchResult(result, report)


def selftest(module: bytes) -> PatchResult:
    """Repack with no edits; output must be byte identical to the input."""
    if crc16(module) != 0:
        raise ValueError("module fails CRC before selftest")
    out = bytearray(module[:-2])
    out += crc16(bytes(out)).to_bytes(2, "big")
    if bytes(out) != module:
        raise AssertionError("selftest produced different bytes")
    return PatchResult(bytes(out), {"selftest": "identical", "size": len(module)})
