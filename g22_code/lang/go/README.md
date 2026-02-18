## Usage
1. Download and install GO ([Link](https://go.dev/doc/install)).
2. Verify successful installation using `go version`
3. Then run using the following terminal commands:
```bash
go run zip.go c <input file path> <output file path> # compresses input file to output file location
go run zip.go d <input file path> <output file path> # decompresses input file to output file location

# or alternatively (better performance):
go build zip.go
./zip.exe c <input file path> <output file path> # compresses input file to output file location
./zip.exe d <input file path> <output file path> # decompresses input file to output file location
```
