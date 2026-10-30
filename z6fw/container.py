"""Z6 firmware container: decrypt, parse, extract/repack modules.

Layout (from the decrypted image):
  file 0x00  : 32-byte plaintext header  [20-byte SHA-1 digest][12 bytes]
  file 0x20  : body, XOR-encrypted from body offset 0x20 onward
  body 0x00  : 32 ASCII spaces (plaintext label)
  body 0x20  : BE32 module count | BE32 directory size | 8 zero bytes
  body 0x30  : count x [16-byte name][BE32 offset][BE32 length][8 zero bytes]
               modules (each ending in a BE16 CRC), then BE16 package CRC + 14 zeros
"""
from __future__ import annotations

import binascii
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HDR = 0x20          # plaintext header length
LABEL = 32          # body label length
DIR_OFF = 0x20      # directory header offset inside the body
TRAILER = 16        # BE16 package CRC + 14 zero bytes


def crc16(data: bytes) -> int:
    """CRC-16/CCITT, polynomial 0x1021, init 0, no reflection, no final xor."""
    return binascii.crc_hqx(data, 0)


def crc_ok(module: bytes) -> bool:
    """A whole module (payload + its BE16 CRC) has residue 0."""
    return crc16(module) == 0


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Key:
    t1: np.ndarray
    t2: np.ndarray
    t3: np.ndarray

    @classmethod
    def load(cls, path: str | Path) -> "Key":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        tables = []
        for name in ("T1", "T2", "T3"):
            blob = bytes.fromhex(raw[name])
            if len(blob) != 256:
                raise ValueError("%s is %d bytes, expected 256" % (name, len(blob)))
            got = sha256(blob)
            recorded = (raw.get("self_check") or {}).get(name)
            if recorded and recorded != got:
                raise ValueError("%s fails its recorded hash" % name)
            tables.append(np.frombuffer(blob, dtype=np.uint8))
        return cls(*tables)


@dataclass(frozen=True)
class Module:
    name: str
    offset: int      # offset inside the body
    length: int      # includes the trailing BE16 CRC
    data: bytes

    @property
    def payload(self) -> bytes:
        return self.data[:-2]


def decrypt_image(image: bytes, key: Key) -> bytes:
    """Return the image with the body decoded; header and label untouched."""
    if len(image) < HDR + LABEL:
        raise ValueError("image too short")
    if image[HDR:HDR + LABEL] != b" " * LABEL:
        raise ValueError("no 32-space label at 0x20: not a legacy-scheme image")
    out = np.frombuffer(image, dtype=np.uint8).copy()
    idx = np.arange(HDR + LABEL, len(out), dtype=np.int64)
    body_off = idx - HDR
    ks = (key.t1[body_off & 0xFF]
          ^ key.t2[(body_off >> 8) & 0xFF]
          ^ key.t3[(body_off >> 16) & 0xFF])
    out[HDR + LABEL:] ^= ks.astype(np.uint8)
    return out.tobytes()


def encrypt_image(plain: bytes, key: Key) -> bytes:
    return decrypt_image(plain, key)  # XOR is its own inverse


@dataclass(frozen=True)
class Parsed:
    header: bytes
    body: bytes
    modules: tuple[Module, ...]

    def module(self, name: str) -> Module:
        for m in self.modules:
            if m.name == name:
                return m
        raise KeyError(name)


def parse(decrypted: bytes) -> Parsed:
    header = decrypted[:HDR]
    body = decrypted[HDR:]
    if body[:LABEL] != b" " * LABEL:
        raise ValueError("body label is not 32 spaces")
    count, dirsize = struct.unpack_from(">II", body, DIR_OFF)
    if dirsize != 48 + 32 * count:
        raise ValueError("directory size %d does not match 48+32*%d" % (dirsize, count))
    if body[DIR_OFF + 8:DIR_OFF + 16] != b"\x00" * 8:
        raise ValueError("reserved bytes are not zero")
    modules = []
    for i in range(count):
        off = 0x30 + 32 * i
        name = body[off:off + 16].split(b"\x00")[0].decode("latin-1")
        moff, mlen = struct.unpack_from(">II", body, off + 16)
        if body[off + 24:off + 32] != b"\x00" * 8:
            raise ValueError("module %s has non-zero reserved bytes" % name)
        modules.append(Module(name, moff, mlen, body[moff:moff + mlen]))
    return Parsed(header, body, tuple(modules))


def load(image_path: str | Path, key_path: str | Path) -> Parsed:
    key = Key.load(key_path)
    parsed = parse(decrypt_image(Path(image_path).read_bytes(), key))
    return parsed


def check_structure(parsed: Parsed) -> list[str]:
    """Return a list of structural problems (empty means clean)."""
    problems = []
    body = parsed.body
    end = len(body) - TRAILER
    chained = sorted(parsed.modules, key=lambda m: m.offset)
    expect = 0x30 + 32 * len(chained)
    for m in chained:
        if m.offset != expect:
            problems.append("module %s starts at 0x%X, expected 0x%X" % (m.name, m.offset, expect))
        expect = m.offset + m.length
        if not crc_ok(m.data):
            problems.append("module %s fails CRC residue" % m.name)
    if expect != end:
        problems.append("modules end at 0x%X, trailer starts at 0x%X" % (expect, end))
    stored = struct.unpack(">H", body[-TRAILER:-TRAILER + 2])[0]
    computed = crc16(body[:-TRAILER])
    if stored != computed:
        problems.append("package CRC 0x%04X != computed 0x%04X" % (stored, computed))
    if body[-TRAILER + 2:] != b"\x00" * 14:
        problems.append("package trailer padding is not zero")
    return problems


def replace_module(parsed: Parsed, name: str, new_module: bytes) -> bytes:
    """Swap one module in the body and return a new decrypted image.

    Module length must be unchanged: the directory stores fixed offsets and the
    whole-file size must stay stable for the packaging to remain valid.
    """
    old = parsed.module(name)
    if len(new_module) != old.length:
        raise ValueError("module %s length would change (%d -> %d)"
                         % (name, old.length, len(new_module)))
    body = bytearray(parsed.body)
    body[old.offset:old.offset + old.length] = new_module
    body[-TRAILER:-TRAILER + 2] = crc16(bytes(body[:-TRAILER])).to_bytes(2, "big")
    return parsed.header + bytes(body)
