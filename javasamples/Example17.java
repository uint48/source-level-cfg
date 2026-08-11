package example;

// Un-braced bodies, a dangling `else`, and an `else if` chain.
//
// Un-braced bodies enter no `Block`, which the old string-toggle used as its
// signal for "we are in the then-branch" -- so a `return` in an un-braced then
// was filed into the else branch instead. The dangling-else form parses as the
// grammar's `*NoShortIf` variants, which had no handler at all.
public class Example17 {
    public static int sign(int n) {
        if (n > 0) return 1;
        else if (n < 0) return -1;
        else return 0;
    }

    public static String size(int n) {
        if (n < 10) {
            return "tiny";
        } else if (n < 100) {
            return "small";
        } else if (n < 1000) {
            return "medium";
        } else {
            return "large";
        }
    }

    public static void danglingElse(int a, int b) {
        if (a > 0)
            if (b > 0)
                System.out.println("both positive");
            else
                System.out.println("a positive, b not");
        else
            System.out.println("a not positive");
    }

    public static void unbracedLoops(int n) {
        for (int i = 0; i < n; i++)
            System.out.println(i);

        int j = 0;
        while (j < n)
            j++;
    }
}
