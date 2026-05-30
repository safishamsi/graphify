#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SIZE 256

typedef struct {
    int width;
    int height;
} Rectangle;

static int validate(const char *input) {
    return input != NULL && strlen(input) > 0;
}

char *process(const char *input) {
    if (!validate(input)) {
        return NULL;
    }
    char *result = malloc(MAX_SIZE);
    strncpy(result, input, MAX_SIZE - 1);
    return result;
}

Rectangle *make_rect(Rectangle *defaults) {
    Rectangle *r = malloc(sizeof(Rectangle));
    if (defaults) {
        r->width = defaults->width;
        r->height = defaults->height;
    }
    return r;
}

int main(int argc, char *argv[]) {
    char *out = process("hello");
    if (out) {
        printf("%s\n", out);
        free(out);
    }
    return 0;
}
