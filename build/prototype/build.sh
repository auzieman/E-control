#!/bin/sh
set -eu
mkdir -p build/out
cc -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -O2 src/preview.c src/audio.c src/displays.c src/accounts.c src/workstation.c -o build/out/workstation-settings $(pkg-config --cflags --libs elementary glib-2.0) -lm
edje_cc -id assets src/frost.edc -o build/out/frost.edj
cp tools/audio-provider.py build/out/audio-provider.py
cp tools/display-provider.py build/out/display-provider.py
cp tools/workstation-provider.py build/out/workstation-provider.py
cp tools/settings-provider.py build/out/settings-provider.py
cp backend/helper.py build/out/settings_core.py
pkg-config --modversion elementary > build/out/efl-version.txt
sha256sum build/out/workstation-settings build/out/frost.edj build/out/audio-provider.py build/out/display-provider.py build/out/settings-provider.py build/out/settings_core.py build/out/workstation-provider.py > build/out/SHA256SUMS
