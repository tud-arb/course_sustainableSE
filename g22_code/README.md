# Energy Consumption of `gzip` Across Programming Languages

This repository evaluates the **energy consumption and runtime** of `gzip` compression and decompression across, C++, Java, Go, Python. Experiments use deterministic datasets and are executed with **EnergiBridge**.

---

# 1. Generate Deterministic Input Data

All datasets are generated using:

```
data/generate_input.py
```

## Requirements

- Python 3.9+
- Works on Windows / Linux / macOS

---

## Generate Compressible Dataset (JSONL)
From the repository root (`g22_code/`):

```bash
python data/generate_input.py --type compressible --mb 64
```

Output:

```
data/input_compressible_64MB.jsonl
```

---

## Generate Incompressible Dataset (Uniform Random Bytes)
From the repository root (`g22_code/`):

```bash
python data/generate_input.py --type incompressible --mb 64
```

Output:

```
data/input_incompressible_64MB.bin
```

---

## Determinism

The generator uses a fixed default seed. For identical:

- `--type`
- `--mb`
- `--seed`

you will get identical bytes.

The script prints a SHA-256 hash for reproducibility.

---

## Linux/macOS Notes

Use:

```bash
python3 data/generate_input.py ...
sha256sum file
```

On Windows:

```bat
certutil -hashfile file SHA256
```

---

# 2. Language Implementations

All implementations expose the same interface:

```
<program> c input output.gz     # compress
<program> d input.gz output     # decompress
```

Compression level is fixed to **6** in all languages.

---

## 2.1 C++

### Requirements

- `g++`
- `zlib` development libraries

### Compile

```bash
g++ -O2 -std=c++17 lang/cpp/zip.cpp -o lang/cpp/zip -lz
```

### Run

```bash
lang/cpp/zip c input output.gz
lang/cpp/zip d input.gz output
```

---

## 2.2 Java

### Requirements

- JDK 8+

### Compile

```bash
mkdir -p lang/java/bin
javac -d lang/java/bin lang/java/Zip.java
```

### Run

```bash
java -cp lang/java/bin Zip c input output.gz
java -cp lang/java/bin Zip d input.gz output
```

---

## 2.3 Go

### Requirements

- Go installed

### Build

```bash
go build -o lang/go/zip lang/go/zip.go
```

### Run

```bash
lang/go/zip c input output.gz
lang/go/zip d input.gz output
```

---

## 2.4 Python

Uses built-in `gzip` module.

```bash
python3 lang/python/zip.py c input output.gz
python3 lang/python/zip.py d input.gz output
```

---

# 3. Correctness Check

Correctness means:

1. **Round-trip integrity**

   ```
   decompress(compress(input)) == input
   ```

2. **Standards compatibility**
   Files must interoperate with GNU gzip / Python gzip / 7-Zip.

---

## 3.1 Round-Trip Test

Example (C++):

```bash
lang/cpp/zip c input.jsonl out.gz
lang/cpp/zip d out.gz roundtrip.jsonl
```

Compare hashes:

```bash
sha256sum input.jsonl
sha256sum roundtrip.jsonl
```

Hashes must match. Repeat similarly for Java, Go, and Python.

---

## 3.2 Cross-Compatibility

You can validate:

- Decompress your `.gz` using Python
- Compress with Python and decompress using your implementation
- Decompress using GNU gzip or 7-Zip

If hashes match, the implementation is functional.

---

# 4. Energy Measurements with EnergiBridge

Experiments are run via:

```
scripts/run_all_experiments.py
```

Each language is evaluated on:

- compressible + compress
- compressible + decompress
- incompressible + compress
- incompressible + decompress

Total: **4 experiment groups per language**

---

## 4.1 Requirements

You must have:

- EnergiBridge (`energibridge`)
- GNU gzip (`gzip`)
- g++
- javac
- go
- python3

Check availability:

```bash
energibridge --version
gzip --version
g++ --version
javac -version
go version
python3 --version
```

---

# 5. Running the Full Experiment

## Recommended Scientific Setup

```bash
python3 scripts/run_all_experiments.py \
  --energibridge energibridge \
  --mb 256 \
  --runs 30 \
  --warmup 3 \
  --rest-s 60 \
  --seed 12345 \
  --shuffle-seed 123 \
  --interval-us 100 \
  --keep-raw
```

---

## Quick Test Run

```bash
python3 scripts/run_all_experiments.py \
  --energibridge energibridge \
  --mb 64 \
  --runs 1 \
  --warmup 1 \
  --rest-s 1
```

---

## What the Runner Controls

- Deterministic input generation
- Reference `.gz` files via GNU gzip (`-6 -n`)
- Warm-up runs
- Repeated measurements
- Rest between runs
- Shuffled language execution order
- Full configuration saved in `config.json`

---

## Recommended Manual Controls

Before long runs:

- Close unnecessary programs
- Disable updates/notifications
- Keep hardware configuration fixed
- Avoid background downloads
- Use stable power mode

These reduce measurement noise.

---

# 6. Results Folder Structure

Each experiment creates:

```
results/<timestamp>/
```

Structure:

```
results/
  <timestamp>/
    config.json
    data/
    compressible/
      compress/
        cpp/
        java/
        go/
        python/
      decompress/
        ...
    incompressible/
      compress/
      decompress/
```

Each language folder contains:

- `metrics.csv` (analysis-ready)
- `artifacts/` (output files)
- `raw/` (EnergiBridge logs if --keep-raw)

---

# 7. Collected Metrics

Each `metrics.csv` contains one row per measured run.

Base columns:

- `run`
- `return_code`
- `wall_time_s`
- `compression_ratio`
- `energy_per_mb_j`
- `dataset`
- `mode`
- `lang`
- `input`
- `output`

Plus all numeric EnergiBridge fields (e.g. `total_energy_j`).