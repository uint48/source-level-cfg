package example;

// Early and multiple returns, `for (;;)` with `break`, and code after a return.
//
// The old generator handled a return by deleting one successor node outright,
// which could remove a join block that was still reachable from elsewhere, then
// reattached the resulting orphans by scanning block ids downward.
public class Example20 {
    public static int find(int[] values, int target) {
        if (values == null) {
            return -1;
        }
        for (int i = 0; i < values.length; i++) {
            if (values[i] == target) {
                return i;
            }
        }
        return -1;
    }

    public static int countdown(int start) {
        int n = start;
        for (;;) {
            if (n <= 0) {
                break;
            }
            System.out.println(n);
            n--;
        }
        return n;
    }

    public static int unreachableTail(int n) {
        if (n > 0) {
            return n;
        }
        return -n;
    }

    public static void infiniteLoop() {
        while (true) {
            System.out.println("forever");
        }
    }
}
