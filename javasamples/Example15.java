package example;

// Arrow-form `switch` (Java 14+), which never falls through. The grammar's
// `switchRule` alternative was not handled at all before, so these bodies were
// dropped from the graph.
public class Example15 {
    public static void main(String[] args) {
        int day = args.length;

        switch (day) {
            case 1, 7 -> System.out.println("weekend");
            case 2, 3, 4, 5, 6 -> {
                System.out.println("weekday");
                System.out.println("work");
            }
            default -> throw new IllegalArgumentException("bad day");
        }

        System.out.println("done");
    }
}
