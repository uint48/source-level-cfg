package example;

public class Example10 {
    public static void main(String[] args) {
        int totalIterations = 10;

        int whileCounter = 1;
        while (whileCounter <= totalIterations) {
            System.out.println(whileCounter);
            whileCounter++;
        }

        for (int i = 1; i <= totalIterations; i++) {
            System.out.println("test");
        }

        int doWhileCounter = 1;
        do {
            if (doWhileCounter % 3 == 0) {
                System.out.println("Divisible by 3: " + doWhileCounter);
            } else if (doWhileCounter % 5 == 0) {
                System.out.println("Divisible by 5: " + doWhileCounter);
            } else {
                System.out.println("Not divisible by 3 or 5: " + doWhileCounter);
            }
            doWhileCounter++;
        } while (doWhileCounter <= totalIterations);
    }
}
