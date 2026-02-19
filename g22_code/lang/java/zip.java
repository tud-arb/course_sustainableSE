import java.io.*;
import java.util.zip.*;

public class Zip {

    private static final int CHUNK_SIZE = 1 << 15; // 32KB
    private static final int COMPRESSION_LEVEL = 6;

    // Custom GZIPOutputStream that sets Deflater level (Java 8 compatible)
    static class LevelGZIPOutputStream extends GZIPOutputStream {
        LevelGZIPOutputStream(OutputStream out, int size, int level) throws IOException {
            super(out, size);
            this.def.setLevel(level);
        }
    }

    private static int gzipCompress(String inputPath, String outputPath) {
        try (BufferedInputStream in = new BufferedInputStream(new FileInputStream(inputPath), CHUNK_SIZE);
             BufferedOutputStream fileOut = new BufferedOutputStream(new FileOutputStream(outputPath), CHUNK_SIZE);
             GZIPOutputStream gzOut = new LevelGZIPOutputStream(fileOut, CHUNK_SIZE, COMPRESSION_LEVEL)) {

            byte[] buffer = new byte[CHUNK_SIZE];
            int read;
            while ((read = in.read(buffer)) != -1) {
                gzOut.write(buffer, 0, read);
            }
            // Close will finish the gzip stream.
            return 0;

        } catch (IOException e) {
            System.err.println("Compression failed: " + e.getMessage());
            return 1;
        }
    }

    private static int gzipDecompress(String inputPath, String outputPath) {
        try (BufferedInputStream fileIn = new BufferedInputStream(new FileInputStream(inputPath), CHUNK_SIZE);
             GZIPInputStream gzIn = new GZIPInputStream(fileIn, CHUNK_SIZE);
             BufferedOutputStream out = new BufferedOutputStream(new FileOutputStream(outputPath), CHUNK_SIZE)) {

            byte[] buffer = new byte[CHUNK_SIZE];
            int read;
            while ((read = gzIn.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            return 0;

        } catch (IOException e) {
            System.err.println("Decompression failed: " + e.getMessage());
            return 1;
        }
    }

    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println("Usage:\n"
                    + "  compress:   java Zip c input output.gz\n"
                    + "  decompress: java Zip d input.gz output\n");
            System.exit(1);
        }

        String mode = args[0];
        String input = args[1];
        String output = args[2];

        int rc;
        if ("c".equals(mode)) rc = gzipCompress(input, output);
        else if ("d".equals(mode)) rc = gzipDecompress(input, output);
        else {
            System.err.println("Invalid mode. Use 'c' for compress or 'd' for decompress.");
            rc = 1;
        }

        System.exit(rc);
    }
}
