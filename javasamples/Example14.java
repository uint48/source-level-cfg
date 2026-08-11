package example;

// Colon-form `switch`: deliberate fall-through, a multi-label group, and a
// `default` that is not last. The old representation keyed cases by label text
// in a dict, so `case 2, 3:` kept only "3", and fall-through edges were drawn
// from the start of the previous case body instead of its end.
public class Example14 {
    public static String classify(int value) {
        String name = "";
        switch (value) {
            case 0:
                name = "zero";
                break;
            case 1:
                name = "one";
                // falls through
            case 2:
            case 3:
                name = name + " small";
                break;
            default:
                name = "many";
                break;
            case 99:
                name = "sentinel";
        }
        return name;
    }

    public static void main(String[] args) {
        for (int i = 0; i < 4; i++) {
            System.out.println(classify(i));
        }
    }
}
