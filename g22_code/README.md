# Energy Consumption of File Compression Across Programming Languages

## 1. Generate deterministic input files

### Requirements
- Python 3.9+ (any modern Python 3 should work)

### Generate a compressible dataset (JSONL, log-like)
From the repository root (`g22_code/`):

```bash
python data/generate_input.py --type compressible --mb 64
```

Default output:
* `data/input_compressible_64MB.jsonl`

### Generate an incompressible dataset (uniform random bytes)
```bash
python data/generate_input.py --type incompressible --mb 64
```

Default output:
* `data/input_incompressible_64MB.bin`

### Custom output path (optional)
```bash
python data/generate_input.py --type compressible --mb 256 --out data/myfile.jsonl
```

### Determinism / replication
The generator uses a fixed default seed, so for the same:
* `--type`
* `--mb`
* `--seed` (if provided)

… you will get the exact same bytes every time.

The script prints a SHA-256 hash of the generated file so you can verify your replication package.

---

## Linux notes (hashing + running Python)

On Linux/macOS:

* use `python3` instead of `python`
* use `sha256sum` instead of `certutil`

Examples:

```bash
python3 data/generate_input.py --type compressible --mb 64
sha256sum data/input_compressible_64MB.jsonl
```

---

## 2. Build and run the C++ implementation

### Requirements (Windows + MSYS2 UCRT64)

You need:
* `g++` (MinGW-w64 toolchain)
* `zlib` headers and library

If using MSYS2 UCRT64, install zlib once:
```bash
pacman -S --needed mingw-w64-ucrt-x86_64-zlib
```

### Compile
From the repository root (using the MSYS2 UCRT64 g++):
```bat
C:\msys64\ucrt64\bin\g++.exe -O2 -std=c++17 lang\cpp\zip.cpp -o lang\cpp\zip.exe -lz
```

If compilation succeeds, you will have:
* `lang/cpp/zip.exe`

### Run: compress
```bat
lang\cpp\zip.exe c data\input_compressible_64MB.jsonl data\out.gz
```

### Run: decompress
```bat
lang\cpp\zip.exe d data\out.gz data\roundtrip.jsonl
```

---

## 2b. Build and run the Java implementation (gzip level 6)

Java uses `java.util.zip.GZIPOutputStream` / `GZIPInputStream` and sets compression level **6**.

### Requirements (Windows)

* JDK 8+ installed (`javac` and `java` available)

### Compile (Windows)

From the repository root:

```bat
mkdir lang\java\bin
javac -d lang\java\bin lang\java\Zip.java
```

### Run: compress (Windows)

```bat
java -cp lang\java\bin Zip c data\input_compressible_64MB.jsonl data\out_java.gz
```

### Run: decompress (Windows)

```bat
java -cp lang\java\bin Zip d data\out_java.gz data\roundtrip_java.jsonl
```

## 2c. Build and run Python implementation
Python uses the built-in `gzip` module, which is a wrapper around zlib and is standards-compliant.

```bat
python zip.py c  input_file  output_file.gz      # compress
python zip.py d  input_file.gz  output_file      # decompress
```


## 3. Test that compressible output is correct
Correctness is defined as:
1. **Round-trip integrity:**
   `decompress(compress(input)) == input` (byte-for-byte identical)

2. **Standards compatibility (recommended):**
   A reference gzip implementation can:

   * decompress your `.gz`
   * produce `.gz` files that your program can decompress


## A. Round-trip test (mandatory)
This verifies that the compressor and decompressor work together correctly.

### 1. Compress
```bat
lang\cpp\zip.exe c data\input_compressible_64MB.jsonl data\out.gz
```

### 2. Decompress
```bat
lang\cpp\zip.exe d data\out.gz data\roundtrip.jsonl
```

### 3. Compare hashes (must match exactly)
```bat
certutil -hashfile data\input_compressible_64MB.jsonl SHA256
certutil -hashfile data\roundtrip.jsonl SHA256
```

If the SHA256 values are identical, the implementation is correct.

---

## A2. Round-trip test for Java

### 1. Compress (Java)

```bat
java -cp lang\java\bin Zip c data\input_compressible_64MB.jsonl data\out_java.gz
```

### 2. Decompress (Java)

```bat
java -cp lang\java\bin Zip d data\out_java.gz data\roundtrip_java.jsonl
```

### 3. Compare hashes (Windows)

```bat
certutil -hashfile data\input_compressible_64MB.jsonl SHA256
certutil -hashfile data\roundtrip_java.jsonl SHA256
```

### 3. Compare hashes (Linux/macOS)

```bash
sha256sum data/input_compressible_64MB.jsonl
sha256sum data/roundtrip_java.jsonl
```

---

## B. Cross-check using Python
Python’s built-in `gzip` module uses zlib and is standards-compliant. This is the simplest way to verify compatibility on Windows.


### Decompress the resulting `.gz` using Python
```bat
python -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/out.gz','rb'), open('data/python_roundtrip.jsonl','wb'))"
```

Compare hashes:
```bat
certutil -hashfile data\input_compressible_64MB.jsonl SHA256
certutil -hashfile data\python_roundtrip.jsonl SHA256
```

If hashes match, the compressor produces valid gzip output.


### Compress using Python, decompress using the implementation

```bat
python -c "import gzip, shutil; shutil.copyfileobj(open('data/input_compressible_64MB.jsonl','rb'), gzip.open('data/python_ref.gz','wb'))"
```

Now decompress with the implementation:

```bat
lang\cpp\zip.exe d data\python_ref.gz data\from_python.jsonl
```

Compare:

```bat
certutil -hashfile data\input_compressible_64MB.jsonl SHA256
certutil -hashfile data\from_python.jsonl SHA256
```

If the hashes match, the decompressor is compatible with standard gzip output.

---

## B2. Cross-check Java gzip compatibility using Python (optional)

### Decompress Java `.gz` using Python

Windows:

```bat
python -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/out_java.gz','rb'), open('data/python_roundtrip_java.jsonl','wb'))"
certutil -hashfile data\input_compressible_64MB.jsonl SHA256
certutil -hashfile data\python_roundtrip_java.jsonl SHA256
```

Linux/macOS:

```bash
python3 -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/out_java.gz','rb'), open('data/python_roundtrip_java.jsonl','wb'))"
sha256sum data/input_compressible_64MB.jsonl
sha256sum data/python_roundtrip_java.jsonl
```

### Compress using Python, decompress using Java

Windows:

```bat
python -c "import gzip, shutil; shutil.copyfileobj(open('data/input_compressible_64MB.jsonl','rb'), gzip.open('data/python_ref.gz','wb'))"
java -cp lang\java\bin Zip d data\python_ref.gz data\from_python_java.jsonl
certutil -hashfile data\input_compressible_64MB.jsonl SHA256
certutil -hashfile data\from_python_java.jsonl SHA256
```

Linux/macOS:

```bash
python3 -c "import gzip, shutil; shutil.copyfileobj(open('data/input_compressible_64MB.jsonl','rb'), gzip.open('data/python_ref.gz','wb'))"
java -cp lang/java/bin Zip d data/python_ref.gz data/from_python_java.jsonl
sha256sum data/input_compressible_64MB.jsonl
sha256sum data/from_python_java.jsonl
```

---

## C. Cross-check using 7-Zip (GUI option)

If you have 7-Zip installed:

### 1. Decompress your `.gz`
* Right-click `data/out.gz`
* Choose **7-Zip → Extract Here**

### 2. Compare hashes
```bat
certutil -hashfile data\input_compressible_64MB.jsonl SHA256
certutil -hashfile data\extracted_filename.jsonl SHA256
```

If the hashes match, the `.gz` file is valid.

Additionally, you can also:

* Compress the input file using 7-Zip (gzip format)
* Decompress it with your program
* Compare hashes as above

## 4. Test that the incompressible output is correct

The methodology is exactly the same as for the compressible input. The only difference is that for a true incompressible file (uniform random bytes), the output size should be almost the same as input, or possibly slightly larger (gzip header + metadata overhead)

### Check file sizes
```bat
lang\cpp\zip.exe c data\input_incompressible_64MB.bin data\incomp.gz
lang\cpp\zip.exe d data\incomp.gz data\incomp_roundtrip.bin
certutil -hashfile data\input_incompressible_64MB.bin SHA256
certutil -hashfile data\incomp_roundtrip.bin SHA256

dir data\input_incompressible_64MB.bin
dir data\incomp.gz
```

Expected behavior is for the .gz size to be approximately the same as the original size, sometimes slightly larger (~0.1–1% overhead).

---

## 4b. Incompressible test for Java

### Compress + decompress (Java)

Windows:

```bat
java -cp lang\java\bin Zip c data\input_incompressible_64MB.bin data\incomp_java.gz
java -cp lang\java\bin Zip d data\incomp_java.gz data\incomp_roundtrip_java.bin
certutil -hashfile data\input_incompressible_64MB.bin SHA256
certutil -hashfile data\incomp_roundtrip_java.bin SHA256
```

Linux/macOS:

```bash
java -cp lang/java/bin Zip c data/input_incompressible_64MB.bin data/incomp_java.gz
java -cp lang/java/bin Zip d data/incomp_java.gz data/incomp_roundtrip_java.bin
sha256sum data/input_incompressible_64MB.bin
sha256sum data/incomp_roundtrip_java.bin
```

Check file sizes:
Windows:

```bat
dir data\input_incompressible_64MB.bin
dir data\incomp_java.gz
```

Linux/macOS:

```bash
ls -lh data/input_incompressible_64MB.bin data/incomp_java.gz
```

Expected behavior is for the `.gz` size to be approximately the same as the original size, sometimes slightly larger (~0.1–1% overhead).


---

## 5. EnergiBridge measurements (all languages)


We measure energy consumption using **EnergiBridge** while running each language implementation on two datasets (compressible + incompressible) and two operations (compress + decompress), for a total of **4 experiment groups**:

* compressible + compress
* compressible + decompress
* incompressible + compress
* incompressible + decompress

### 5.1 Requirements

#### EnergiBridge

You need an EnergiBridge binary available either in your `PATH` or via an explicit path.

Check availability:

* Linux/macOS: `which energibridge`
* Windows: `where energibridge`

#### GNU gzip (for reference `.gz`)

For fair decompression measurements we use a **single fixed reference `.gz`** for each dataset, generated with **GNU gzip**:

* `gzip -6 -n -c INPUT > ref.gz`

The `-n` flag removes filename and timestamp from the gzip header, improving reproducibility.

Check availability:

```bash
gzip --version
```

> If `gzip` is missing on Windows, install it via WSL / Git Bash / MSYS2 / Cygwin, or run the experiments in a Linux environment.

---

### 5.2 Running the full experiment (recommended)

Use the orchestrator script:

```bash
python3 scripts/run_all_experiments.py --langs java cpp --energibridge energibridge
```

This will:

1. Create a new experiment folder under `results/<datetime>/`
2. Generate the two input files in `results/<datetime>/data/`
3. Generate the two **reference `.gz`** files using **GNU gzip** (`gzip -6 -n`)
4. Run all four experiment groups and record EnergiBridge measurements

Common options (all applied uniformly to every experiment group):

```bash
python3 scripts/run_all_experiments.py \
  --langs java cpp \
  --energibridge energibridge \
  --mb 64 \
  --runs 30 \
  --warmup 3 \
  --rest-s 60 \
  --seed 12345 \
  --shuffle-seed 123 \
  --interval-us 100 \
  --keep-raw
```

**Meaning of parameters:**

* `--mb`: size of generated inputs (in MB)
* `--runs`: number of measured runs per condition (default 30)
* `--warmup`: number of warm-up runs per condition (discarded)
* `--rest-s`: sleep time between measured runs (reduces temperature drift)
* `--seed`: deterministic input generation seed
* `--shuffle-seed`: deterministic shuffle seed (interleaves languages within each block)
* `--interval-us`: EnergiBridge sampling interval in microseconds
* `--keep-raw`: keep per-run EnergiBridge CSV/log files (recommended for debugging/auditing)

---

### 5.3 Results folder structure

Each experiment creates:

```
results/
  <datetime>/
    config.json
    data/
      input_compressible_<MB>MB.jsonl
      input_incompressible_<MB>MB.bin
      ref_compressible_level6_<MB>MB.gz
      ref_incompressible_level6_<MB>MB.gz

    compressible/
      compress/
        <lang>/
          metrics.csv
          artifacts/
          raw/                (only if --keep-raw)
      decompress/
        <lang>/
          metrics.csv
          artifacts/
          raw/                (only if --keep-raw)

    incompressible/
      compress/
        <lang>/
          metrics.csv
          artifacts/
          raw/                (only if --keep-raw)
      decompress/
        <lang>/
          metrics.csv
          artifacts/
          raw/                (only if --keep-raw)
```

* `config.json`: records the experiment configuration (mb, runs, warmup, rest, seeds, etc.)
* `data/`: contains generated inputs and reference gzip files
* `artifacts/`: contains output files produced by the implementations (e.g., `.gz` for compression, roundtrip outputs for decompression)
* `raw/`: contains per-run EnergiBridge CSV/log files (if enabled)
* `metrics.csv`: **analysis-ready table** with **one row per run**

---

### 5.4 What metrics are collected

EnergiBridge writes a **CSV per run** (e.g., `raw/run_1.csv`) when invoked with `--summary`.
Our scripts parse that CSV and append the numeric fields into a single file:

* `metrics.csv` (one row per run)

`metrics.csv` always includes these base fields:

* `run`: run number (1..N)
* `return_code`: command return code (0 = success)
* `wall_time_s`: elapsed wall time of the run (seconds)
* `dataset`: compressible / incompressible
* `mode`: compress / decompress
* `lang`: language name
* `input`, `output`: paths used for the run

Additionally, it includes **all numeric columns reported by EnergiBridge** on your system (e.g., total energy, CPU package energy, duration, etc.). The exact available columns can vary by OS/hardware/EnergiBridge version, so the recommended workflow is:

* Use `metrics.csv` for analysis (already merged)
* Use `raw/run_k.csv` for auditing/debugging a specific outlier run (if `--keep-raw`)

---