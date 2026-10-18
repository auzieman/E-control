#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
arch=$(pkg-config --variable=module_arch enlightenment)
case "$arch" in ''|*[!a-zA-Z0-9_.-]*) exit 1;; esac
mkdir -p "build/out/workstation_settings/$arch"
cc -std=gnu11 -fPIC -shared -Wall -Wextra -O2 $(pkg-config --cflags enlightenment) \
 modules/workstation_settings/e_mod_main.c -o "build/out/workstation_settings/$arch/module.so" \
 $(pkg-config --libs enlightenment)
cp modules/workstation_settings/module.desktop build/out/workstation_settings/
printf '%s\n' "$arch"
