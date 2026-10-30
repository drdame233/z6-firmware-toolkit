"""Mappings measured from the unmodified Z6 C 3.80 EG module.

All addresses are ARM addresses as seen at run time; the module loads at BASE.
Subtract BASE to obtain a module-relative offset, which is what the patch tool
and the build reports use.
"""

BASE = 0x10020000
MODULE_NAME = "eg1620_038000.bi"
STOCK_SIZE = 33_502_842                     # payload + 2-byte CRC
STOCK_SHA256 = "1e6348d58750e67372d0a8e363932c57ee9c04d0eb8f62803bcd19812df0d25c"
VERSION_STRING = "Ver.03.80.00"             # at module offset 0x20

# --- container metadata -------------------------------------------------
SCATTER_TABLE = 0x14000                     # module offset of the scatter descriptors
SCATTER = (
    (0x11E94DD4, 0xC1800000, 0x00101400),   # rom -> ram, 1 MiB
    (0x11F96200, 0xC2A10000, 0x00000FF8),
    (0x11F97200, 0xC9200000, 0x0007C478),
)

# --- JPEG output size table --------------------------------------------
# 12 records of 6 bytes: (u16 width, u16 height, u16 aspect_id)
# aspect_id 0 = 3:2 (FX and DX), 3 = 1:1, 4 = 16:9
SIZE_TABLE = 0x1065FDD0
SIZE_RECORD = 6
SIZE_TABLE_READER_LITERAL = 0x103C3464      # the only 32-bit literal reference
SIZE_QUERY_CODE = 0x103C2FB8                # code region owning that literal pool

# module-relative offsets of the fields we patch
OFF_W_FX_L, OFF_H_FX_L, OFF_ID_FX_L = 0x63FDD0, 0x63FDD2, 0x63FDD4
OFF_H_169_L = SIZE_TABLE + 9 * SIZE_RECORD + 2 - BASE
OFF_H_169_M = SIZE_TABLE + 10 * SIZE_RECORD + 2 - BASE
OFF_H_169_S = SIZE_TABLE + 11 * SIZE_RECORD + 2 - BASE

STOCK_169_HEIGHT = {"L": 3400, "M": 2544, "S": 1696}   # 16:9 = aspect_id 4
STOCK_169_WIDTH = {"L": 6048, "M": 4528, "S": 3024}

# --- crop geometry (partially located) ---------------------------------
# The crop rectangle is computed, not stored as a literal (x,y,w,h) tuple:
#   psVar3 = (short *)(*r2 + (short)r2[10] * 0x14)
#   x = center_x - psVar3[0]/2 ; y = center_y - psVar3[1]/2
# so the source table has stride 0x14 and (w,h) at +0/+2. Base not yet resolved.
CROP_TABLE_STRIDE = 0x14
CROP_CODE_REGION = (0x103C2FB8, 0x103C3460)

# The sensor readout window is NOT stored as literal (x,y,w,h) tuples: searches for
# (0,312,6048,3400), (312,3400), (1012,0,4024,4024) and (1056,700,3936,2624) all
# returned zero hits, while the size table itself is present verbatim. The window is
# therefore derived in code from the aspect selection. Until that code is patched,
# changing only the output size table makes the camera resample the existing 16:9
# window into the new height, i.e. the image is squeezed, not cropped.
CROP_GEOMETRY_PATCHED = False

# --- audio (phase 3 investigation) -------------------------------------
WAV_TEMPLATE_OFFSET = 0x4DB84               # header without sizes, used by A:\TEST%04d.WAV
WAV_ASSET_OFFSET = 0x14A64F4                # 48 kHz stereo 16-bit, ~60 s (11.52 MB)
AUDIO_EVENT_TABLE = 0x1E8F930               # AFAssistLight / ShutterDrive / Beep / Key / ChangeLV
BEEP_ERROR_STRINGS = "BeepPlay failed / BeepPlay was timeout"


def off(address: int) -> int:
    """ARM address -> module-relative offset."""
    return address - BASE


def addr(offset: int) -> int:
    """Module-relative offset -> ARM address."""
    return BASE + offset
