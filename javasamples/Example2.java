package example;

public class Example2 {
    public static void main(String[] args) {
        for (int i = 1, j = 1; i <= 3; i++, j++) {
            for (int k = 1, l = 1; k <= 2; k++, l++) {
                System.out.println("i: " + i + ", j: " + j + ", k: " + k + ", l: " + l);
            }
        }
    }
}
