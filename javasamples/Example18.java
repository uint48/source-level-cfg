package example;

// Expression shapes that the parser used to mangle: `>>>` (the operator was
// built from the wrong tokens, yielding `>>` with `>` as the operand), field
// access (turned into a binary expression rendered `a . b`), and `instanceof`.
//
// Ternaries and short-circuit `&&` / `||` stay as single conditions here: this
// is a source-level CFG and does not expand them into branches. See the
// README's non-goals.
public class Example18 {
    private int count = 3;

    public int shifts(int v) {
        int a = v << 2;
        int b = v >> 1;
        int c = v >>> 3;
        return a + b + c;
    }

    public String describe(Object o) {
        if (o instanceof String s) {
            return "string of length " + s.length();
        }
        if (o instanceof Integer) {
            return "boxed int";
        }
        return "unknown";
    }

    public int ternaryAndShortCircuit(int[] values, int index) {
        int fallback = this.count > 0 ? this.count : -1;

        if (values != null && index >= 0 && index < values.length) {
            return values[index];
        }
        if (values == null || index < 0) {
            return fallback;
        }
        return 0;
    }
}
