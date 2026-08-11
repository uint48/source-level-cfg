package example;

// Degenerate and boundary shapes. Each of these caught a real bug once the
// invariant checker was pointed at it:
//
//  - `if (c) {} else {}` leaves two empty arms whose `true` and `false` edges
//    reach the same join. Contracting both would have overwritten one label and
//    silently lost a branch, since a DiGraph holds one edge per node pair.
//  - `switch (n) {}` has no cases, so a dispatch block would have had a single
//    successor and no case to label it with.
//  - a `switch` whose only label is `default` legitimately has one successor.
//  - nested `try`/`finally` must keep the normal and abrupt paths out of each
//    `finally` distinct.
public class Example25 {

    void emptyBody() {}

    void onlySemicolons() { ; ; ; }

    void emptyBlocks() { { } { { } } }

    void emptyIf(int n) {
        if (n > 0) {} else {}
    }

    void emptyLoops(int n) {
        for (int i = 0; i < n; i++) {}
        while (n > 0) {}
    }

    void emptySwitch(int n) {
        switch (n) { }
    }

    void switchWithOnlyDefault(int n) {
        switch (n) {
            default:
                break;
        }
    }

    void switchWithoutDefault(int n) {
        switch (n) {
            case 1:
                System.out.println("one");
                break;
        }
    }

    void nestedTryFinally() {
        try {
            try {
                System.out.println("inner");
            } catch (RuntimeException e) {
                throw e;
            } finally {
                System.out.println("inner finally");
            }
        } catch (Exception e) {
            System.out.println("outer");
        } finally {
            System.out.println("outer finally");
        }
    }

    int returnInsideFinally() {
        try {
            return 1;
        } finally {
            return 2;
        }
    }

    void deeplyNestedUnbraced(int n) {
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++)
                for (int k = 0; k < n; k++)
                    if (i == j)
                        if (j == k) System.out.println(i);
                        else continue;
                    else break;
    }

    void throwOnly() {
        throw new RuntimeException("always");
    }
}
