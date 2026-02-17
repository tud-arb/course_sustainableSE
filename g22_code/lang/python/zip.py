"""
Pure Python Gzip Compress / Decompress
=======================================
100% Python — NO C extensions (no zlib, no gzip module).
Implements: CRC-32, DEFLATE (fixed Huffman + LZ77), gzip file format (RFC 1952).

Usage:
    python zip.py c  input_file  output_file.gz      # compress
    python zip.py d  input_file.gz  output_file      # decompress
"""

import struct
import sys
import time


# ─────────────────────────────────────────────────────────────────────────────
# PURE PYTHON CRC-32  (replaces zlib.crc32)
# ─────────────────────────────────────────────────────────────────────────────

def _make_crc_table():
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            if c & 1:
                c = 0xEDB88320 ^ (c >> 1)
            else:
                c >>= 1
        table.append(c)
    return table

_CRC_TABLE = _make_crc_table()


def crc32(data: bytes, crc: int = 0) -> int:
    """Pure-Python CRC-32 compatible with zlib.crc32 output."""
    crc = crc ^ 0xFFFFFFFF
    table = _CRC_TABLE
    for b in data:
        crc = table[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF


# ─────────────────────────────────────────────────────────────────────────────
# BIT I/O
# ─────────────────────────────────────────────────────────────────────────────

class BitWriter:
    """Writes bits LSB-first into a bytearray."""
    __slots__ = ("buf", "_byte", "_bit")

    def __init__(self):
        self.buf = bytearray()
        self._byte = 0
        self._bit = 0

    def write_bits(self, value: int, n: int):
        for i in range(n):
            if (value >> i) & 1:
                self._byte |= (1 << self._bit)
            self._bit += 1
            if self._bit == 8:
                self.buf.append(self._byte)
                self._byte = 0
                self._bit = 0

    def flush(self):
        if self._bit:
            self.buf.append(self._byte)
            self._byte = 0
            self._bit = 0

    def get_bytes(self) -> bytes:
        self.flush()
        return bytes(self.buf)


class BitReader:
    """Reads bits LSB-first from a bytes object."""
    __slots__ = ("_data", "_pos", "_bit")

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0
        self._bit = 0

    def read_bits(self, n: int) -> int:
        result = 0
        for i in range(n):
            if self._pos >= len(self._data):
                raise ValueError("Unexpected end of compressed data")
            bit = (self._data[self._pos] >> self._bit) & 1
            result |= (bit << i)
            self._bit += 1
            if self._bit == 8:
                self._bit = 0
                self._pos += 1
        return result

    def align_to_byte(self):
        if self._bit:
            self._bit = 0
            self._pos += 1


# ─────────────────────────────────────────────────────────────────────────────
# FIXED HUFFMAN TABLES  (RFC 1951 §3.2.6)
# ─────────────────────────────────────────────────────────────────────────────

def _reverse_bits(v: int, n: int) -> int:
    r = 0
    for _ in range(n):
        r = (r << 1) | (v & 1)
        v >>= 1
    return r


def _build_fixed_lit_len_codes():
    """Build encoder table: symbol -> (reversed_code, bit_length)."""
    codes = {}
    for i in range(144):
        codes[i] = (i + 0x30, 8)
    for i in range(144, 256):
        codes[i] = (i - 144 + 0x190, 9)
    for i in range(256, 280):
        codes[i] = (i - 256, 7)
    for i in range(280, 288):
        codes[i] = (i - 280 + 0xC0, 8)
    return {s: (_reverse_bits(c, b), b) for s, (c, b) in codes.items()}


FIXED_LIT_LEN = _build_fixed_lit_len_codes()


# Length table  (RFC 1951 Table 1)  — symbol 257..285
LEN_TABLE = [
    (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0),
    (9, 0), (10, 0), (11, 1), (13, 1), (15, 1), (17, 1),
    (19, 2), (23, 2), (27, 2), (31, 2), (35, 3), (43, 3),
    (51, 3), (59, 3), (67, 4), (83, 4), (99, 4), (115, 4),
    (131, 5), (163, 5), (195, 5), (227, 5), (258, 0),
]

# Distance table  (RFC 1951 Table 2)  — distance code 0..29
DIST_TABLE = [
    (1, 0), (2, 0), (3, 0), (4, 0),
    (5, 1), (7, 1), (9, 2), (13, 2),
    (17, 3), (25, 3), (33, 4), (49, 4),
    (65, 5), (97, 5), (129, 6), (193, 6),
    (257, 7), (385, 7), (513, 8), (769, 8),
    (1025, 9), (1537, 9), (2049, 10), (3073, 10),
    (4097, 11), (6145, 11), (8193, 12), (12289, 12),
    (16385, 13), (24577, 13),
]


def _encode_length(length: int):
    """Return (symbol, extra_bits_count, extra_value) for a match length."""
    for i, (base, extra) in enumerate(LEN_TABLE):
        nxt = LEN_TABLE[i + 1][0] if i + 1 < len(LEN_TABLE) else 259
        if base <= length < nxt:
            return 257 + i, extra, length - base
    return 285, 0, 0


def _encode_distance(dist: int):
    """Return (dist_code, extra_bits_count, extra_value) for a distance."""
    for code, (base, extra) in enumerate(DIST_TABLE):
        nxt = DIST_TABLE[code + 1][0] if code + 1 < len(DIST_TABLE) else 32769
        if base <= dist < nxt:
            return code, extra, dist - base
    return 29, 13, dist - 24577


def _decode_length(symbol: int, br: BitReader) -> int:
    """Given a lit/len symbol 257..285, read extra bits and return length."""
    idx = symbol - 257
    base, extra = LEN_TABLE[idx]
    return base + (br.read_bits(extra) if extra else 0)


def _decode_distance(code: int, br: BitReader) -> int:
    """Given a distance code 0..29, read extra bits and return distance."""
    base, extra = DIST_TABLE[code]
    return base + (br.read_bits(extra) if extra else 0)


# ─────────────────────────────────────────────────────────────────────────────
# DEFLATE COMPRESSOR  (fixed Huffman + LZ77)
# ─────────────────────────────────────────────────────────────────────────────

def _deflate_compress(data: bytes) -> bytes:
    bw = BitWriter()

    # Block header: BFINAL=1, BTYPE=01 (fixed Huffman)
    bw.write_bits(1, 1)   # BFINAL
    bw.write_bits(1, 1)   # BTYPE low
    bw.write_bits(0, 1)   # BTYPE high

    n = len(data)
    i = 0
    WIN = 32768
    MAX_LEN = 258
    MIN_LEN = 3

    # Hash-chain LZ77
    hash_chains: dict[int, list[int]] = {}

    def _h3(p: int) -> int:
        return (data[p] << 10) ^ (data[p + 1] << 5) ^ data[p + 2]

    while i < n:
        best_len = 0
        best_dist = 0

        if i + MIN_LEN <= n:
            h = _h3(i)
            chain = hash_chains.get(h)
            if chain is not None:
                limit = min(MAX_LEN, n - i)
                for pos in chain:
                    d = i - pos
                    if d < 1 or d > WIN:
                        continue
                    ml = 0
                    while ml < limit and data[pos + ml] == data[i + ml]:
                        ml += 1
                    if ml >= MIN_LEN and ml > best_len:
                        best_len = ml
                        best_dist = d
                        if ml == MAX_LEN:
                            break
            # Update chain (keep newest 16 entries within window)
            if chain is None:
                hash_chains[h] = [i]
            else:
                chain.insert(0, i)
                if len(chain) > 16:
                    del chain[16:]

        if best_len >= MIN_LEN:
            sym, le, lv = _encode_length(best_len)
            code, bits = FIXED_LIT_LEN[sym]
            bw.write_bits(code, bits)
            if le:
                bw.write_bits(lv, le)

            dc, de, dv = _encode_distance(best_dist)
            bw.write_bits(_reverse_bits(dc, 5), 5)
            if de:
                bw.write_bits(dv, de)

            # Insert hashes for skipped positions
            for j in range(1, best_len):
                p = i + j
                if p + MIN_LEN <= n:
                    hj = _h3(p)
                    cj = hash_chains.get(hj)
                    if cj is None:
                        hash_chains[hj] = [p]
                    else:
                        cj.insert(0, p)
                        if len(cj) > 16:
                            del cj[16:]
            i += best_len
        else:
            code, bits = FIXED_LIT_LEN[data[i]]
            bw.write_bits(code, bits)
            i += 1

    # End-of-block (symbol 256)
    code, bits = FIXED_LIT_LEN[256]
    bw.write_bits(code, bits)

    return bw.get_bytes()


# ─────────────────────────────────────────────────────────────────────────────
# DEFLATE DECOMPRESSOR
# ─────────────────────────────────────────────────────────────────────────────

def _build_fixed_decode_table():
    """
    Build decode lookup: (canonical_code, bit_length) -> symbol
    for the fixed Huffman alphabet.
    """
    table = {}
    for sym, (rev_code, bits) in FIXED_LIT_LEN.items():
        canonical = _reverse_bits(rev_code, bits)
        table[(canonical, bits)] = sym
    return table


_FIXED_DECODE = _build_fixed_decode_table()


def _decode_fixed_symbol(br: BitReader) -> int:
    """Decode one literal/length symbol from a fixed Huffman block."""
    code = 0
    for length in range(1, 16):
        code = (code << 1) | br.read_bits(1)
        sym = _FIXED_DECODE.get((code, length))
        if sym is not None:
            return sym
    raise ValueError("Invalid fixed Huffman code in stream")


def _build_huffman_tree(lengths):
    """
    Build a Huffman decode table from a list of code lengths.
    Returns dict: (canonical_code, bit_length) -> symbol
    """
    max_bits = max((l for l in lengths if l), default=0)
    if max_bits == 0:
        return {}

    bl_count = [0] * (max_bits + 1)
    for ln in lengths:
        if ln:
            bl_count[ln] += 1

    next_code = [0] * (max_bits + 2)
    code = 0
    for bits in range(1, max_bits + 1):
        code = (code + bl_count[bits - 1]) << 1
        next_code[bits] = code

    table = {}
    for sym, ln in enumerate(lengths):
        if ln:
            table[(next_code[ln], ln)] = sym
            next_code[ln] += 1
    return table


def _decode_symbol(br: BitReader, table: dict) -> int:
    """Decode one symbol given a Huffman table."""
    code = 0
    for length in range(1, 16):
        code = (code << 1) | br.read_bits(1)
        sym = table.get((code, length))
        if sym is not None:
            return sym
    raise ValueError("Invalid Huffman code in stream")


# Code-length alphabet order (RFC 1951 §3.2.7)
_CL_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]


def _deflate_decompress(raw: bytes) -> bytes:
    """Decompress a raw DEFLATE stream (fixed, dynamic, and stored blocks)."""
    br = BitReader(raw)
    output = bytearray()

    while True:
        bfinal = br.read_bits(1)
        btype = br.read_bits(2)

        if btype == 0:
            # ── Stored (uncompressed) block ──
            br.align_to_byte()
            ln = br.read_bits(16)
            nln = br.read_bits(16)
            if ln != (~nln & 0xFFFF):
                raise ValueError("Stored block length mismatch")
            for _ in range(ln):
                output.append(br.read_bits(8))

        elif btype == 1:
            # ── Fixed Huffman block ──
            while True:
                sym = _decode_fixed_symbol(br)
                if sym < 256:
                    output.append(sym)
                elif sym == 256:
                    break
                else:
                    length = _decode_length(sym, br)
                    dist_code = _reverse_bits(br.read_bits(5), 5)
                    dist = _decode_distance(dist_code, br)
                    start = len(output) - dist
                    for k in range(length):
                        output.append(output[start + k])

        elif btype == 2:
            # ── Dynamic Huffman block ──
            hlit = br.read_bits(5) + 257
            hdist = br.read_bits(5) + 1
            hclen = br.read_bits(4) + 4

            # Read code-length code lengths
            cl_lengths = [0] * 19
            for i in range(hclen):
                cl_lengths[_CL_ORDER[i]] = br.read_bits(3)
            cl_table = _build_huffman_tree(cl_lengths)

            # Read literal/length + distance code lengths
            all_lengths = []
            total = hlit + hdist
            while len(all_lengths) < total:
                sym = _decode_symbol(br, cl_table)
                if sym < 16:
                    all_lengths.append(sym)
                elif sym == 16:
                    repeat = br.read_bits(2) + 3
                    all_lengths.extend([all_lengths[-1]] * repeat)
                elif sym == 17:
                    repeat = br.read_bits(3) + 3
                    all_lengths.extend([0] * repeat)
                elif sym == 18:
                    repeat = br.read_bits(7) + 11
                    all_lengths.extend([0] * repeat)

            lit_table = _build_huffman_tree(all_lengths[:hlit])
            dist_table = _build_huffman_tree(all_lengths[hlit:hlit + hdist])

            while True:
                sym = _decode_symbol(br, lit_table)
                if sym < 256:
                    output.append(sym)
                elif sym == 256:
                    break
                else:
                    length = _decode_length(sym, br)
                    dc = _decode_symbol(br, dist_table)
                    dist = _decode_distance(dc, br)
                    start = len(output) - dist
                    for k in range(length):
                        output.append(output[start + k])
        else:
            raise ValueError(f"Invalid BTYPE={btype}")

        if bfinal:
            break

    return bytes(output)


# ─────────────────────────────────────────────────────────────────────────────
# GZIP FILE FORMAT  (RFC 1952)
# ─────────────────────────────────────────────────────────────────────────────

_GZIP_MAGIC = b"\x1f\x8b"


def gzip_compress(data: bytes) -> bytes:
    """Wrap raw data in a valid gzip container (pure Python)."""
    deflated = _deflate_compress(data)
    crc = crc32(data)
    header = bytes([
        0x1F, 0x8B,                     # magic
        0x08,                            # method = DEFLATE
        0x00,                            # flags
        0x00, 0x00, 0x00, 0x00,          # mtime
        0x00,                            # xfl
        0xFF,                            # OS = unknown
    ])
    footer = struct.pack("<II", crc, len(data) & 0xFFFFFFFF)
    return header + deflated + footer


def gzip_decompress(gz: bytes) -> bytes:
    """Decompress a gzip byte-stream (pure Python)."""
    if gz[:2] != _GZIP_MAGIC:
        raise ValueError("Not a gzip file (bad magic)")
    if gz[2] != 8:
        raise ValueError("Unsupported compression method")

    flags = gz[3]
    pos = 10

    # FEXTRA
    if flags & 0x04:
        xlen = gz[pos] | (gz[pos + 1] << 8)
        pos += 2 + xlen
    # FNAME
    if flags & 0x08:
        while gz[pos] != 0:
            pos += 1
        pos += 1
    # FCOMMENT
    if flags & 0x10:
        while gz[pos] != 0:
            pos += 1
        pos += 1
    # FHCRC
    if flags & 0x02:
        pos += 2

    # Last 8 bytes = CRC32 + ISIZE
    footer = gz[-8:]
    expected_crc = struct.unpack("<I", footer[:4])[0]
    expected_size = struct.unpack("<I", footer[4:])[0]

    raw_deflate = gz[pos:-8]
    decompressed = _deflate_decompress(raw_deflate)

    actual_crc = crc32(decompressed)
    if actual_crc != expected_crc:
        raise ValueError(
            f"CRC mismatch: expected {expected_crc:#010x}, got {actual_crc:#010x}"
        )
    if (len(decompressed) & 0xFFFFFFFF) != expected_size:
        raise ValueError("Size mismatch")

    return decompressed


# ─────────────────────────────────────────────────────────────────────────────
# PURITY VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def verify_pure_python():
    """
    Prove at runtime that no C-extension compression module is loaded.
    Checks every module in sys.modules against a ban list.
    """
    BANNED = {"zlib", "gzip", "_compression", "bz2", "lzma", "_lzma", "_bz2"}
    loaded = BANNED & set(sys.modules)
    if loaded:
        raise RuntimeError(
            f"C-extension module(s) {loaded} imported — NOT pure Python!"
        )
    print("[OK] Purity check passed: no C compression extensions loaded.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN  — CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 4:
        print("Pure-Python gzip compressor / decompressor")
        print()
        print("Usage:")
        print("  python zip.py c  <input_file>  <output_file.gz>   # compress")
        print("  python zip.py d  <input_file.gz>  <output_file>   # decompress")
        sys.exit(1)

    mode = sys.argv[1].lower()
    input_path = sys.argv[2]
    output_path = sys.argv[3]

    verify_pure_python()

    with open(input_path, "rb") as f:
        data = f.read()

    input_size = len(data)
    t0 = time.perf_counter()

    if mode == "c":
        result = gzip_compress(data)
        elapsed = time.perf_counter() - t0
        with open(output_path, "wb") as f:
            f.write(result)
        ratio = len(result) / input_size * 100 if input_size else 0
        print(f"Compressed {input_size:,} -> {len(result):,} bytes "
              f"({ratio:.1f}%) in {elapsed:.3f}s")

    elif mode == "d":
        result = gzip_decompress(data)
        elapsed = time.perf_counter() - t0
        with open(output_path, "wb") as f:
            f.write(result)
        print(f"Decompressed {input_size:,} -> {len(result):,} bytes "
              f"in {elapsed:.3f}s")

    else:
        print(f"Unknown mode '{mode}'. Use 'c' (compress) or 'd' (decompress).")
        sys.exit(1)


if __name__ == "__main__":
    main()



