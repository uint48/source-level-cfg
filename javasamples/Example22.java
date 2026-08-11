package example;

// An interface with `default` and `static` methods, plus an implementing class.
// `interfaceMethodDeclaration` is a separate grammar rule from
// `methodDeclaration`, so these bodies were never visited before. The abstract
// method has no body and correctly produces no CFG.
public interface Example22 {

    int apply(int value);

    default int applyTwice(int value) {
        int once = apply(value);
        if (once == value) {
            return once;
        }
        return apply(once);
    }

    static int clamp(int value, int max) {
        if (value < 0) {
            return 0;
        }
        if (value > max) {
            return max;
        }
        return value;
    }
}
