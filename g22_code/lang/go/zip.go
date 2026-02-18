package main

import "compress/gzip"
import "fmt"
import "io"
import "os"

func main() {
	if len(os.Args) != 4 {
		fmt.Println("Usage: go run main.go <mode> <input> <output>")
		fmt.Println("mode: c for compress, d for decompress")
		fmt.Println("input: path to file to compress")
		fmt.Println("output: path to file to output")
		os.Exit(1)
	}

	mode := os.Args[1]
	inputPath := os.Args[2]
	outputPath := os.Args[3]

	inFile, err := os.Open(inputPath)
	check_error(err)
	defer inFile.Close()

	outFile, err := os.Create(outputPath)
	check_error(err)
	defer outFile.Close()

	if mode == "c" {
		compress(inFile, outFile)
		fmt.Println("Successfully compressed input file.")
	} else if mode == "d" {
		decompress(inFile, outFile)
		fmt.Println("Successfully decompressed input file.")
	}
}

func compress(inFile *os.File, outFile *os.File) {
	gzWriter, err := gzip.NewWriterLevel(outFile, 6)
	check_error(err)
	defer gzWriter.Close()

	_, err = io.Copy(gzWriter, inFile)
	check_error(err)
}

func decompress(inFile *os.File, outFile *os.File) {
	gzReader, err := gzip.NewReader(inFile)
	check_error(err)
	defer gzReader.Close()

	_, err = io.Copy(outFile, gzReader)
	check_error(err)
}

func check_error(err error) {
	if err != nil {
		fmt.Println(err.Error())
		os.Exit(1)
	}
}
