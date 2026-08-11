package example;

import java.util.List;
import java.util.function.Function;

// Lambdas, method references, and an anonymous class.
//
// A lambda body used to be spliced into the enclosing method's CFG, mixing
// statements that never run together into one graph. Each now becomes its own
// method -- `<enclosing>$lambda$N` for a lambda, `<Type>$anonN.<method>` for an
// anonymous class -- so the enclosing graph shows only the statement that
// creates it.
public class Example23 {

    public static void main(String[] args) {
        List<String> names = List.of("ada", "grace", "alan");

        names.forEach(name -> {
            if (name.startsWith("a")) {
                System.out.println("a-name: " + name);
            } else {
                System.out.println("other: " + name);
            }
        });

        Function<Integer, Integer> square = n -> n * n;
        System.out.println(square.apply(5));

        names.forEach(System.out::println);

        Runnable task = new Runnable() {
            @Override
            public void run() {
                for (int i = 0; i < 3; i++) {
                    System.out.println("tick " + i);
                }
            }
        };
        task.run();
    }
}
