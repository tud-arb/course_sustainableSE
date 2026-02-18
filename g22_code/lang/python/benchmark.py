"""
Benchmark Runner for Python Gzip Compression
=============================================
Runs zip.py compress+decompress on every file in an input folder,
repeats N times, and records runtime & compression ratio per iteration.

Results are written to a CSV file in the output folder.

Usage:
    python benchmark.py <input_folder> <output_folder> <iterations>

Example:
    python benchmark.py ./test_data ./results 30

Output CSV columns:
    file, iteration, original_bytes, compressed_bytes,
    compression_ratio, compress_time_s, decompress_time_s,
    total_time_s, original_mb, compress_time_per_mb_s,
    energy_joules (placeholder — populated when EnergiBridge is available)
"""

import csv
import os
import pathlib
import subprocess
import sys
import time


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ZIP_SCRIPT = SCRIPT_DIR / "zip.py"


def discover_files(input_folder: pathlib.Path) -> list[pathlib.Path]:
    """Return a sorted list of regular files in *input_folder*."""
    files = sorted(
        p for p in input_folder.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    if not files:
        print(f"ERROR: no files found in {input_folder}")
        sys.exit(1)
    return files


def run_zip(mode: str, src: str, dst: str) -> tuple[float, str]:
    """
    Invoke zip.py as a subprocess and return (wall_time_seconds, stdout).
    """
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(ZIP_SCRIPT), mode, src, dst],
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"  zip.py {mode} failed:\n    {result.stderr.strip()}")
    return elapsed, result.stdout.strip()


def benchmark(input_folder: pathlib.Path,
              output_folder: pathlib.Path,
              iterations: int) -> list[dict]:
    """
    Compress + decompress every file in *input_folder* for *iterations*
    rounds and return a list of result dicts.
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    files = discover_files(input_folder)

    print(f"Input folder : {input_folder}  ({len(files)} file(s))")
    print(f"Output folder: {output_folder}")
    print(f"Iterations   : {iterations}")
    print()

    rows: list[dict] = []

    for src in files:
        original_size = src.stat().st_size
        original_mb = original_size / (1024 * 1024)
        gz_path = output_folder / (src.name + ".gz")
        dec_path = output_folder / (src.name + ".decompressed")

        print(f"  {src.name}  ({original_size:,} bytes / {original_mb:.2f} MB)")

        for it in range(1, iterations + 1):
            # ── compress ──
            compress_time, _ = run_zip("c", str(src), str(gz_path))

            compressed_size = gz_path.stat().st_size if gz_path.exists() else 0
            compression_ratio = (
                compressed_size / original_size if original_size else 0.0
            )

            # ── decompress ──
            decompress_time, _ = run_zip("d", str(gz_path), str(dec_path))

            total_time = compress_time + decompress_time
            compress_per_mb = compress_time / original_mb if original_mb else 0.0

            row = {
                "file": src.name,
                "iteration": it,
                "original_bytes": original_size,
                "compressed_bytes": compressed_size,
                "compression_ratio": round(compression_ratio, 6),
                "compress_time_s": round(compress_time, 6),
                "decompress_time_s": round(decompress_time, 6),
                "total_time_s": round(total_time, 6),
                "original_mb": round(original_mb, 6),
                "compress_time_per_mb_s": round(compress_per_mb, 6),
                "energy_joules": "",  # placeholder for EnergiBridge
            }
            rows.append(row)

            if it % 10 == 0 or it == iterations:
                print(f"    iteration {it}/{iterations}  "
                      f"ratio={compression_ratio:.4f}  "
                      f"compress={compress_time:.4f}s  "
                      f"decompress={decompress_time:.4f}s")

        # Clean up temporary decompressed file
        if dec_path.exists():
            dec_path.unlink()

    return rows


def write_csv(rows: list[dict], output_folder: pathlib.Path) -> pathlib.Path:
    """Write result rows to a CSV and return its path."""
    csv_path = output_folder / "benchmark_results.csv"
    fieldnames = [
        "file", "iteration", "original_bytes", "compressed_bytes",
        "compression_ratio", "compress_time_s", "decompress_time_s",
        "total_time_s", "original_mb", "compress_time_per_mb_s",
        "energy_joules",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def print_summary(rows: list[dict]):
    """Print a per-file summary table to stdout."""
    files = sorted(set(r["file"] for r in rows))
    print()
    print(f"{'File':<30} {'Iters':>5} {'Ratio':>8} "
          f"{'Avg Compress':>14} {'Avg Decompress':>16} {'Avg Total':>11}")
    print("-" * 90)
    for fname in files:
        fr = [r for r in rows if r["file"] == fname]
        n = len(fr)
        avg_ratio = sum(r["compression_ratio"] for r in fr) / n
        avg_comp = sum(r["compress_time_s"] for r in fr) / n
        avg_dec = sum(r["decompress_time_s"] for r in fr) / n
        avg_tot = sum(r["total_time_s"] for r in fr) / n
        print(f"{fname:<30} {n:>5} {avg_ratio:>8.4f} "
              f"{avg_comp:>13.4f}s {avg_dec:>15.4f}s {avg_tot:>10.4f}s")


def main():
    if len(sys.argv) != 4:
        print("Benchmark runner for Python gzip compression")
        print()
        print("Usage:")
        print("  python benchmark.py <input_folder> <output_folder> <iterations>")
        sys.exit(1)

    input_folder = pathlib.Path(sys.argv[1]).resolve()
    output_folder = pathlib.Path(sys.argv[2]).resolve()
    iterations = int(sys.argv[3])

    if not input_folder.is_dir():
        print(f"ERROR: '{input_folder}' is not a directory")
        sys.exit(1)
    if iterations < 1:
        print("ERROR: iterations must be >= 1")
        sys.exit(1)

    rows = benchmark(input_folder, output_folder, iterations)
    csv_path = write_csv(rows, output_folder)
    print_summary(rows)
    print(f"\nResults saved to {csv_path}")


if __name__ == "__main__":
    main()
