package example;

import java.util.List;

// Enhanced `for`, over an array and over a collection.
//
// Both are modeled as an iterator loop -- `has next(...)` in the header,
// `v = next(...)` opening the body. The old rewrite emitted an index loop with a
// hard-coded `.length`, which is simply wrong for anything that is not an array,
// and there is no type resolution here to tell the two apart.
public class Example19 {
    public static int sumArray(int[] numbers) {
        int total = 0;
        for (int n : numbers) {
            total += n;
        }
        return total;
    }

    public static void printNames(List<String> names) {
        for (String name : names) {
            if (name.isEmpty()) {
                continue;
            }
            System.out.println(name);
        }
    }

    public static int firstNegative(int[][] grid) {
        for (int[] row : grid) {
            for (int cell : row) {
                if (cell < 0) {
                    return cell;
                }
            }
        }
        return 0;
    }
}
