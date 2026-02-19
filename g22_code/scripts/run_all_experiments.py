#!/usr/bin/env python3
import argparse
import csv
import json
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# -------------------------
# Build + language commands
# -------------------------

def build_cpp(cpp_src: Path, cpp_bin: Path):
    cpp_bin.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["g++", "-O2", "-std=c++17", str(cpp_src), "-o", str(cpp_bin), "-lz"]
    subprocess.run(cmd, check=True)

def build_java(java_src: Path, java_bin_dir: Path):
    java_bin_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["javac", "-d", str(java_bin_dir), str(java_src)]
    subprocess.run(cmd, check=True)

def command_for_lang(lang: str, repo_root: Path):
    """
    Returns (build_fn, cmd_builder)
    cmd_builder(mode, input_path, output_path) -> list[str]
    """
    if lang == "cpp":
        cpp_src = repo_root / "lang" / "cpp" / "zip.cpp"
        cpp_bin = repo_root / "lang" / "cpp" / "zip"

        def build():
            if not cpp_bin.exists():
                build_cpp(cpp_src, cpp_bin)

        def cmd(mode: str, inp: Path, out: Path):
            return [str(cpp_bin), mode, str(inp), str(out)]

        return build, cmd

    if lang == "java":
        java_src = repo_root / "lang" / "java" / "Zip.java"
        java_bin = repo_root / "lang" / "java" / "bin"

        def build():
            if not (java_bin / "Zip.class").exists():
                build_java(java_src, java_bin)

        def cmd(mode: str, inp: Path, out: Path):
            return ["java", "-cp", str(java_bin), "Zip", mode, str(inp), str(out)]

        return build, cmd

    raise ValueError(f"Unsupported lang: {lang}")


# -------------------------
# Experiment model
# -------------------------

@dataclass(frozen=True)
class Condition:
    dataset: str         # compressible / incompressible
    mode: str            # c / d
    lang: str            # java / cpp

    def dataset_dir(self) -> str:
        return self.dataset

    def mode_dir(self) -> str:
        return "compress" if self.mode == "c" else "decompress"


# -------------------------
# Helpers
# -------------------------

def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

def mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2))

def run(cmd: List[str], *, cwd: Optional[Path] = None, stdout_path: Optional[Path] = None) -> None:
    if stdout_path is None:
        subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None)
    else:
        mkdir(stdout_path.parent)
        with stdout_path.open("w") as f:
            subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None, stdout=f, stderr=subprocess.STDOUT)

def which_or_fail(exe: str) -> str:
    p = shutil.which(exe)
    if not p:
        raise SystemExit(
            f"Required executable '{exe}' not found in PATH.\n"
            f"Install GNU gzip (command: gzip) or ensure it's available in your shell.\n"
            f"Tip: run `gzip --version` to confirm."
        )
    return p

def parse_energibridge_summary(csv_path: Path) -> Dict[str, float]:
    """
    EnergiBridge --summary writes a CSV. We parse the first data row and keep numeric columns.
    This is robust across column naming differences: we store *all* numeric fields we find.
    """
    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader, None)
        if row is None:
            return {}

    out: Dict[str, float] = {}
    for k, v in row.items():
        if v is None:
            continue
        s = str(v).strip()
        if s == "":
            continue
        try:
            out[k] = float(s)
        except ValueError:
            continue

    # Convenience: provide a normalized "total_energy_j" if something like it exists.
    # If it doesn't, we leave it absent (analysis scripts can use the raw columns).
    if "total_energy_j" not in out:
        # Look for likely energy columns
        candidates = [k for k in out.keys() if "energy" in k.lower() and k.lower().endswith(("_j", "joules"))]
        if len(candidates) == 1:
            out["total_energy_j"] = out[candidates[0]]

    return out

def append_metrics_row(metrics_csv: Path, header: List[str], row: Dict[str, object]) -> None:
    mkdir(metrics_csv.parent)
    file_exists = metrics_csv.exists()
    with metrics_csv.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def generate_inputs(out_data_dir: Path, mb: int, seed: int) -> Tuple[Path, Path]:
    """
    Uses your existing generator to create deterministic input files in the experiment's data folder.
    Returns (compressible_path, incompressible_path).
    """
    r = repo_root()
    gen = r / "data" / "generate_input.py"
    if not gen.exists():
        raise SystemExit(f"Missing generator: {gen}")

    comp = out_data_dir / f"input_compressible_{mb}MB.jsonl"
    incomp = out_data_dir / f"input_incompressible_{mb}MB.bin"

    mkdir(out_data_dir)

    run([
        "python3", str(gen),
        "--type", "compressible",
        "--mb", str(mb),
        "--out", str(comp),
        "--seed", str(seed),
    ], cwd=r)

    run([
        "python3", str(gen),
        "--type", "incompressible",
        "--mb", str(mb),
        "--out", str(incomp),
        "--seed", str(seed),
    ], cwd=r)

    return comp, incomp

def make_ref_gz_gnu_gzip(gzip_exe: str, raw_input: Path, ref_gz: Path, level: int = 6) -> None:
    """
    Creates a deterministic-ish ref gzip using GNU gzip:
      gzip -6 -n -c INPUT > ref.gz
    -n removes filename and timestamp from header.
    """
    mkdir(ref_gz.parent)
    cmd = [gzip_exe, f"-{level}", "-n", "-c", str(raw_input)]
    with ref_gz.open("wb") as out:
        subprocess.run(cmd, check=True, stdout=out, stderr=subprocess.PIPE)


# -------------------------
# Main experiment runner
# -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="+", required=True, choices=["cpp", "java"])
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--rest-s", type=float, default=60.0)
    ap.add_argument("--mb", type=int, default=64)
    ap.add_argument("--seed", type=int, default=12345, help="Seed for deterministic input generation.")
    ap.add_argument("--shuffle-seed", type=int, default=123, help="Seed for reproducible interleaving order.")
    ap.add_argument("--interval-us", type=int, default=100)
    ap.add_argument("--energibridge", default="energibridge", help="EnergiBridge executable or absolute path.")
    ap.add_argument("--results-root", default="results")
    ap.add_argument("--keep-raw", action="store_true", help="Keep per-run energibridge CSV/log files (recommended).")
    args = ap.parse_args()

    r = repo_root()

    # Resolve executables
    gzip_exe = which_or_fail("gzip")
    eb_exec = args.energibridge
    # If user provides a path-like string, validate it; otherwise assume it's in PATH.
    eb_path = Path(eb_exec)
    if eb_path.is_absolute() or (eb_path.parent != Path(".")):
        eb_exec = str(eb_path.resolve())
        if not Path(eb_exec).exists():
            raise SystemExit(f"EnergiBridge not found at: {eb_exec}")

    # Build all languages once
    builders: Dict[str, Tuple[callable, callable]] = {}
    for lang in args.langs:
        build, mk_cmd = command_for_lang(lang, r)
        build()
        builders[lang] = (build, mk_cmd)

    # Create experiment root folder
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_root = (r / args.results_root / ts).resolve()
    mkdir(exp_root)

    # Layout folders
    data_dir = exp_root / "data"
    mkdir(data_dir)

    # Config with “comments” via _comment fields (JSON has no real comments)
    config = {
        "_comment_mb": "Size in MB for each generated input dataset.",
        "mb": args.mb,
        "_comment_num_runs": "Number of measured runs per (dataset, mode, language).",
        "num_runs": args.runs,
        "_comment_num_warmup": "Warm-up runs per (dataset, mode, language); executed but not included in metrics.",
        "num_warmup": args.warmup,
        "_comment_rest_seconds": "Sleep between measured runs to reduce thermal drift / scheduling bias.",
        "rest_seconds": args.rest_s,
        "_comment_seed": "Seed for deterministic input generation (same seed => same bytes).",
        "seed": args.seed,
        "_comment_shuffle_seed": "Seed for deterministic shuffling/interleaving order across languages within each block.",
        "shuffle_seed": args.shuffle_seed,
        "_comment_interval_us": "EnergiBridge sampling interval in microseconds.",
        "interval_us": args.interval_us,
        "_comment_ref_gz": "Reference gz files are created with GNU gzip: gzip -6 -n -c INPUT > ref.gz, then used for ALL decompression runs.",
        "ref_gz_tool": "gnu_gzip",
        "energibridge": args.energibridge,
        "langs": args.langs,
        "timestamp": ts,
    }
    write_json(exp_root / "config.json", config)

    # Generate datasets into exp/data/
    comp_in, incomp_in = generate_inputs(data_dir, args.mb, args.seed)

    # Create ref gz (level 6) using GNU gzip
    comp_ref = data_dir / f"ref_compressible_level6_{args.mb}MB.gz"
    incomp_ref = data_dir / f"ref_incompressible_level6_{args.mb}MB.gz"
    make_ref_gz_gnu_gzip(gzip_exe, comp_in, comp_ref, level=6)
    make_ref_gz_gnu_gzip(gzip_exe, incomp_in, incomp_ref, level=6)

    # Define inputs per dataset+mode
    def input_for(dataset: str, mode: str) -> Path:
        if dataset == "compressible" and mode == "c":
            return comp_in
        if dataset == "compressible" and mode == "d":
            return comp_ref
        if dataset == "incompressible" and mode == "c":
            return incomp_in
        if dataset == "incompressible" and mode == "d":
            return incomp_ref
        raise ValueError("bad dataset/mode")

    # Output file naming (unique per run)
    def output_for(cond: Condition, run_idx: int) -> Path:
        lang_dir = exp_root / cond.dataset_dir() / cond.mode_dir() / cond.lang
        out_dir = lang_dir / "artifacts"
        mkdir(out_dir)
        if cond.mode == "c":
            return out_dir / f"out_run{run_idx}.gz"
        else:
            # extension based on dataset
            ext = ".jsonl" if cond.dataset == "compressible" else ".bin"
            return out_dir / f"roundtrip_run{run_idx}{ext}"

    # Where metrics live
    def metrics_csv_for(cond: Condition) -> Path:
        lang_dir = exp_root / cond.dataset_dir() / cond.mode_dir() / cond.lang
        mkdir(lang_dir)
        return lang_dir / "metrics.csv"

    # Raw output directories
    def raw_dir_for(cond: Condition) -> Path:
        lang_dir = exp_root / cond.dataset_dir() / cond.mode_dir() / cond.lang
        return lang_dir / "raw"

    # Run plan: for each (dataset, mode) we do "blocks" 1..runs:
    # each block executes each language once in shuffled order (mitigates drift & ordering bias).
    rng = random.Random(args.shuffle_seed)

    datasets = ["compressible", "incompressible"]
    modes = ["c", "d"]

    for dataset in datasets:
        for mode in modes:
            # Ensure top-level folders exist
            for lang in args.langs:
                mkdir(exp_root / dataset / ("compress" if mode == "c" else "decompress") / lang)

            # Warm-up (discard): run each language warmup times (no shuffle requirement; still ok to shuffle)
            if args.warmup > 0:
                warm_list = [Condition(dataset, mode, lang) for lang in args.langs]
                rng.shuffle(warm_list)
                for w in range(1, args.warmup + 1):
                    for cond in warm_list:
                        _, mk_cmd = builders[cond.lang]
                        inp = input_for(dataset, mode)
                        outp = output_for(cond, run_idx=0)  # warmup output can overwrite; we don't care
                        eb_csv = raw_dir_for(cond) / f"warmup_{w}.csv"
                        eb_log = raw_dir_for(cond) / f"warmup_{w}.log"
                        mkdir(raw_dir_for(cond))

                        lang_cmd = mk_cmd(mode, inp, outp)
                        eb_cmd = [eb_exec, "-o", str(eb_csv), "-i", str(args.interval_us), "--summary", "--"] + lang_cmd

                        run(eb_cmd, cwd=r, stdout_path=eb_log)
                    # short pause between warmup blocks (optional); keep it tiny
                    time.sleep(0.2)

            # Measured runs
            for run_idx in range(1, args.runs + 1):
                block = [Condition(dataset, mode, lang) for lang in args.langs]
                rng.shuffle(block)

                for cond in block:
                    _, mk_cmd = builders[cond.lang]
                    inp = input_for(dataset, mode)
                    outp = output_for(cond, run_idx)

                    # raw files
                    eb_csv = raw_dir_for(cond) / f"run_{run_idx}.csv"
                    eb_log = raw_dir_for(cond) / f"run_{run_idx}.log"
                    mkdir(raw_dir_for(cond))

                    lang_cmd = mk_cmd(mode, inp, outp)
                    eb_cmd = [eb_exec, "-o", str(eb_csv), "-i", str(args.interval_us), "--summary", "--"] + lang_cmd

                    t0 = time.time()
                    rc = 0
                    try:
                        run(eb_cmd, cwd=r, stdout_path=eb_log)
                    except subprocess.CalledProcessError as e:
                        rc = int(e.returncode)
                    t1 = time.time()

                    # Parse energibridge summary and append one row into metrics.csv
                    summary = {}
                    if eb_csv.exists():
                        summary = parse_energibridge_summary(eb_csv)

                    # --- Compute derived metrics ---
                    input_size_bytes = inp.stat().st_size if inp.exists() else 0
                    output_size_bytes = outp.stat().st_size if outp.exists() else 0
                    input_size_mb = input_size_bytes / (1024 * 1024)

                    # Compression ratio = uncompressed / compressed  (>1 means smaller)
                    if mode == "c":
                        compression_ratio = (input_size_bytes / output_size_bytes) if output_size_bytes > 0 else 0.0
                    else:
                        # Decompression: input is compressed, output is uncompressed
                        compression_ratio = (output_size_bytes / input_size_bytes) if input_size_bytes > 0 else 0.0

                    # Energy per MB (joules per megabyte of input)
                    total_energy = summary.get("total_energy_j", None)
                    energy_per_mb_j = round(total_energy / input_size_mb, 6) if (total_energy is not None and input_size_mb > 0) else None

                    row = {
                        "run": run_idx,
                        "return_code": rc,
                        "wall_time_s": round(t1 - t0, 6),
                        "compression_ratio": round(compression_ratio, 6),
                        "energy_per_mb_j": energy_per_mb_j,
                        # keep a couple of identifiers for easy merging later
                        "dataset": dataset,
                        "mode": "compress" if mode == "c" else "decompress",
                        "lang": cond.lang,
                        "input": str(inp.relative_to(r)) if inp.is_relative_to(r) else str(inp),
                        "output": str(outp.relative_to(r)) if outp.is_relative_to(r) else str(outp),
                    }
                    # Add all numeric energibridge fields
                    for k, v in summary.items():
                        row[k] = v

                    # Stable header: base fields + sorted energibridge columns seen so far
                    metrics_path = metrics_csv_for(cond)
                    base_cols = ["run", "return_code", "wall_time_s", "compression_ratio",
                                 "energy_per_mb_j", "dataset", "mode", "lang",
                                 "input", "output"]
                    extra_cols = sorted([k for k in row.keys() if k not in base_cols])
                    header = base_cols + extra_cols
                    append_metrics_row(metrics_path, header, row)

                    # If not keeping raw, delete per-run raw files (but metrics.csv remains)
                    if not args.keep_raw:
                        if eb_csv.exists():
                            eb_csv.unlink(missing_ok=True)
                        if eb_log.exists():
                            eb_log.unlink(missing_ok=True)

                    print(f"[info] {dataset}/{('compress' if mode=='c' else 'decompress')}/{cond.lang} run {run_idx}/{args.runs}")

                    if args.rest_s > 0:
                        time.sleep(args.rest_s)

    print("\n[done]")
    print(f"[info] experiment folder: {exp_root}")


if __name__ == "__main__":
    main()
