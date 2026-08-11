package example;

// `break` and `continue` in each loop form. These previously produced no edges
// at all: they were emitted as statements inside a basic block, so a loop
// containing one had no path to its exit.
public class Example12 {
    public static void main(String[] args) {
        for (int i = 0; i < 10; i++) {
            if (i % 2 == 0) {
                continue;
            }
            if (i > 7) {
                break;
            }
            System.out.println(i);
        }

        int j = 0;
        while (j < 10) {
            j++;
            if (j == 3) {
                continue;
            }
            if (j == 8) {
                break;
            }
            System.out.println(j);
        }

        int k = 0;
        do {
            k++;
            if (k == 2) {
                continue;
            }
            if (k == 5) {
                break;
            }
            System.out.println(k);
        } while (k < 10);
    }
}
