"""
Gzip Compress / Decompress — Standard Library Edition
======================================================
Uses Python's built-in `gzip` module for all heavy lifting.

Usage:
    python zip.py c  input_file  output_file.gz      # compress
    python zip.py d  input_file.gz  output_file      # decompress
"""

import gzip
import sys
import time


def gzip_compress(data: bytes) -> bytes:
    """Compress data into gzip format."""
    return gzip.compress(data, compresslevel=6)


def gzip_decompress(gz: bytes) -> bytes:
    """Decompress gzip data."""
    return gzip.decompress(gz)


def main():
    if len(sys.argv) != 4:
        print("Gzip compressor / decompressor (stdlib)")
        print()
        print("Usage:")
        print("  python zip.py c  <input_file>  <output_file.gz>   # compress")
        print("  python zip.py d  <input_file.gz>  <output_file>   # decompress")
        sys.exit(1)

    mode = sys.argv[1].lower()
    input_path = sys.argv[2]
    output_path = sys.argv[3]

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



