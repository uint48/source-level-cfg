package example;

public class Example4 {
    public static void main(String[] args) {
        int number = 7;

        if (number > 0) {
            System.out.println("The number is positive");
        } else if (number < 0) {
            System.out.println("The number is negative");
        } else if (number % 2 == 0) {
            System.out.println("The number is zero");
            System.out.println("The number is also even");
        } else if (number % 2 != 0) {
            System.out.println("The number is zero");
            System.out.println("The number is also odd");
        } else {
            System.out.println("The number is zero");
            System.out.println("The number is also divisible by 2");
        }
    }
}
