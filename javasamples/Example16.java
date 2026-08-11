package example;

import java.io.IOException;

// `try` / `catch` / multi-catch / `finally` / `throw`. None of these were
// handled before: the statements leaked into the enclosing block with no
// exception edges, so the graph claimed every catch body was unreachable.
public class Example16 {
    public static int read(String path) {
        int result = -1;
        try {
            if (path == null) {
                throw new IllegalArgumentException("null path");
            }
            result = path.length();
            System.out.println("read ok");
        } catch (IllegalArgumentException e) {
            System.out.println("bad argument");
            result = 0;
        } catch (RuntimeException | Error e) {
            System.out.println("fatal");
            return -2;
        } finally {
            System.out.println("cleanup");
        }
        return result;
    }

    public static void plainTry() {
        try {
            System.out.println("attempt");
        } catch (Exception e) {
            System.out.println("failed");
        }
        System.out.println("after");
    }

    public static void finallyOnly() {
        try {
            System.out.println("body");
        } finally {
            System.out.println("always");
        }
    }
}
