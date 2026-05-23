/* An example of an ERROR for some 64-bit architectures,
if "unsigned int" is 32 bits and "size_t" is 64 bits: */
#include <unistd.h>
#include <stdlib.h>
#include <stdlib.h>
void *mymalloc(unsigned int size) { return malloc(size); }

int main()
{
    char *buf;
    size_t len;
    read(0, &len, sizeof(len));
    /* we forgot to check the maximum length */
    /* 64-bit size_t gets truncated to 32-bit unsigned int */
    buf = mymalloc(len);
    read(0, buf, len);
    return 0;
}
