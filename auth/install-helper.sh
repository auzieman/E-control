#!/bin/sh
set -eu
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
[ "$(id -u)" = 0 ]
install -d -m 0755 /usr/libexec/workstation-settings /usr/share/polkit-1/actions
install -m 0644 "$project/backend/helper.py" /usr/libexec/workstation-settings/helper.py
install -m 0755 "$project/auth/settings-helper" /usr/libexec/workstation-settings/settings-helper
install -m 0644 "$project/auth/org.auzietek.workstation-settings.policy" /usr/share/polkit-1/actions/org.auzietek.workstation-settings.policy
