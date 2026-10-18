#!/bin/sh
set -eu
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bundle="$project/build/out"
mkdir -p "$bundle/host"
export WORKSTATION_TITLE="${WORKSTATION_TITLE:-E-control}"
export WORKSTATION_THEME="$bundle/frost.edj"
export WORKSTATION_AUDIO_HELPER="$bundle/audio-provider.py"
export WORKSTATION_DISPLAY_HELPER="$bundle/display-provider.py"
export WORKSTATION_SETTINGS_PROVIDER="$bundle/settings-provider.py"
export WORKSTATION_WORKSTATION_PROVIDER="$bundle/workstation-provider.py"
export WORKSTATION_FACTS="$bundle/host"
export ELM_ENGINE=software_x11 ELM_ACCEL=none
exec "$bundle/workstation-settings" "$@"
