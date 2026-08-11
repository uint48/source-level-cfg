package example;

// Nested and inner classes, initializers, constructors, and overloads.
//
// The old walker held the current class and method in single slots, so a nested
// class clobbered its enclosing one and the methods of both ended up attributed
// to whichever was seen last. Constructors took their name from the whole
// declarator text -- parentheses included -- which is why output filenames had
// to be scrubbed afterwards.
public class Example21 {
    private int value;
    private static int instances;

    static {
        instances = 0;
        System.out.println("class loaded");
    }

    {
        value = -1;
    }

    public Example21() {
        this(0);
    }

    public Example21(int value) {
        this.value = value;
        instances++;
        if (value < 0) {
            this.value = 0;
        }
    }

    public int scale(int factor) {
        return value * factor;
    }

    public int scale(int factor, int offset) {
        if (offset == 0) {
            return scale(factor);
        }
        return value * factor + offset;
    }

    static class Helper {
        int twice(int n) {
            return n + n;
        }
    }

    class Inner {
        int plusOuter(int n) {
            if (n < 0) {
                return value;
            }
            return value + n;
        }
    }
}
