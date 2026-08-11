package example;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;

// try-with-resources, `assert`, and `synchronized` -- none of which the old
// walker recognized.
//
// `assert` is modeled as a branch, because it is one: the failing path raises
// AssertionError and leaves the method. `synchronized` is inlined with explicit
// monitor enter/exit statements, since acquiring a lock does not branch.
public class Example24 {
    private final Object lock = new Object();
    private int total;

    public int countLines(String path) throws IOException {
        int lines = 0;
        try (BufferedReader reader = new BufferedReader(new FileReader(path))) {
            while (reader.readLine() != null) {
                lines++;
            }
        } catch (IOException e) {
            return -1;
        }
        return lines;
    }

    public int average(int[] values) {
        assert values != null : "values must not be null";
        assert values.length > 0;

        int sum = 0;
        for (int v : values) {
            sum += v;
        }
        return sum / values.length;
    }

    public void add(int amount) {
        synchronized (lock) {
            if (amount > 0) {
                total += amount;
            }
        }
    }
}
