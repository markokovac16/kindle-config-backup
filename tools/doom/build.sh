#!/bin/bash
# Builds libdoom.so for the Kindle (armhf, glibc 2.20) with crosstool-NG GCC.
set -e
S=/private/tmp/claude-501/-Users-marko-Desktop/843d9aff-c91e-441d-9934-5a94c989e94a/scratchpad/doom
D=$S/src/doomgeneric/doomgeneric
CC=$S/toolchain/arm-unknown-linux-gnueabihf/bin/arm-unknown-linux-gnueabihf-gcc
SRCS=$(grep '^SRC_DOOM' $D/Makefile | sed 's/SRC_DOOM = //; s/doomgeneric_xlib.o/doomgeneric_koreader.o/; s/\.o/.c/g')
FILES=()
for f in $SRCS; do FILES+=("$D/$f"); done
mkdir -p $S/build
$CC -shared -fPIC -O2 -mcpu=cortex-a7 -mfpu=neon -mfloat-abi=hard \
  -fvisibility=hidden -Wl,-Bsymbolic -Wl,--gc-sections -ffunction-sections -fdata-sections \
  -DNORMALUNIX -DLINUX -D_DEFAULT_SOURCE -DDOOMGENERIC_RESX=320 -DDOOMGENERIC_RESY=200 \
  -Dexit=doom_exit -w -s -o $S/build/libdoom.so "${FILES[@]}" -lm
