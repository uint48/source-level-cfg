package example;

// Labeled `break` and `continue` across nested loops. Labels were parsed into
// nothing at all before: `LabeledStmt` existed but was never constructed, and
// the label on a break/continue was discarded.
public class Example13 {
    public static void main(String[] args) {
        outer:
        for (int i = 0; i < 5; i++) {
            for (int j = 0; j < 5; j++) {
                if (j == 3) {
                    continue outer;
                }
                if (i * j > 6) {
                    break outer;
                }
                System.out.println(i + "," + j);
            }
            System.out.println("end of i " + i);
        }

        search:
        while (true) {
            for (int n = 0; n < 3; n++) {
                if (n == 2) {
                    break search;
                }
            }
        }

        block: {
            System.out.println("in labeled block");
            if (args.length == 0) {
                break block;
            }
            System.out.println("has args");
        }
    }
}
