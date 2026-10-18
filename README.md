# E-control

A native Enlightenment/EFL workstation control panel, developed for AlpinEifyd
on Alpine Linux and X11. It follows the active desktop theme and brings common
settings into a sidebar with focused forms.

Version 0.1.0 is the first public preview. Audio, guarded display trials, NetworkManager
connections, BlueZ devices, appearance, accounts, services and system information
have provider integrations. Storage shows usage and volumes, with file browsing
and a GParted handoff. Some advanced settings still open Enlightenment dialogs;
printing supports basic CUPS workflows, with advanced setup handed off.

## What you can do

| Section | Controls and backend |
| --- | --- |
| Appearance | Embedded theme and wallpaper selectors; native E bridge for apply and advanced settings, including fonts, shelves, modules and gadgets. |
| Displays | Arrange X11 monitors, choose modes and trial a layout with timed restoration unless confirmed. |
| Audio | Choose outputs and microphones, volume/mute and application routing through PulseAudio-compatible `pactl`. |
| Wired | Inspect interfaces and edit IPv4 DHCP/static settings through NetworkManager, with checkpoint confirmation/revert. |
| Wi-Fi | Scan, join open/WPA Personal/WPA3 Personal networks, reconnect saved profiles and forget them. |
| Bluetooth | Discover adapters/devices, pair, connect, disconnect and forget through BlueZ. |
| Firewall | Inspect firewalld state, edit default-zone rules and explicitly start/stop the service; saved rules can be edited while stopped. |
| Accounts | Local account details, password/group administration and account creation through the authenticated helper. |
| Storage | Live filesystem space meters, mounted volumes, drive summaries, file browsing and a GParted handoff. |
| Printing | List printers/jobs, add driverless IPP printers, options/default selection, test pages, removal and job cancellation through CUPS. |
| Software | Cached APK/Flatpak update summaries and an Enaptic launcher. |
| System | OS, kernel, processor, memory and host information. |
| Services | Search OpenRC services; manage selected optional services and default-runlevel startup. Core services remain read-only. |

The panel is a frontend to the workstation's existing services. It does not replace
NetworkManager, BlueZ, CUPS or Enlightenment's configuration machinery. Settings
change only when you use an action; browsing pages reads current state.

## Build and run

Requires a C compiler, pkg-config, Elementary/EFL development files, Edje tools,
GLib development files and Python 3. Runtime integrations use Python D-Bus,
NetworkManager, BlueZ, Pulse-compatible pactl, XRandR, OpenRC, util-linux and
optional firewalld. Printing requires CUPS client commands and a reachable CUPS
server; file browsing uses xdg-open. Advanced handoffs optionally use
nm-connection-editor, blueman-manager, system-config-printer, GParted and Enaptic.
Those companion applications may use other UI toolkits; the panel itself is EFL.
Missing services do not get enabled automatically.

```sh
git clone git@github.com:auzieman/E-control.git
cd E-control
sh build/prototype/build.sh
sh tools/run-local.sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

Run the GUI as your normal desktop user. The default uses the current Elementary
theme. WORKSTATION_FROST_PREVIEW=1 opts into the experimental Frost shell.

## Enlightenment appearance bridge

Build against development headers matching your running Enlightenment version:

```sh
sh modules/workstation_settings/build.sh
```

Copy the resulting `build/out/workstation_settings` directory into
`~/.e/e/modules/`, then enable **Workstation Settings Bridge** in E's Modules
settings. When replacing an existing module, unload it before replacing its
binary and load it again afterwards. Merely replacing its file does not update
the running desktop. The panel detects older bridge interfaces and gives reload
instructions. Wallpaper and theme selectors are embedded; advanced E settings
retain their native dialogs. Applying a theme saves it and restarts E; this is
not a timed, automatically reverting trial.

## Privileged operations

Review `backend/helper.py`, `auth/settings-helper` and the Polkit policy before
installing the optional scoped helper:

```sh
sudo sh auth/install-helper.sh
```

This installs a persistent privileged entrypoint for supported accounts,
firewall and VPN actions. It does not grant the GUI unrestricted root access.
A functioning desktop Polkit authentication agent is required. NetworkManager
and BlueZ also enforce their own service permissions. Installing the helper
does not enable services or apply settings.

## Check your backend connections

From an active X11 desktop session, after building:

```sh
python3 tools/check-backends.py
```

This queries the built providers without applying settings, scanning for new
networks or changing service state. It prints status/counts rather than account,
SSID or device details. An unavailable optional service can produce a failed
check; install/configure the service for the section you intend to use. A passing
read check establishes connectivity, not successful privileged write operations.

If a section cannot connect, check its service is installed and running, the user
has access to the session/system D-Bus, and a Polkit authentication agent is active.
For Appearance, enable the matching bridge module and refresh the page. Restart
the panel after upgrading its executable/providers.

## Validation and limitations

76 Python tests passed for this release; all 18 read-only provider checks passed on the development workstation. The native Alpine build was
visually checked on the active desktop theme. Automated write tests use fixtures;
that does not establish every operation on every host. Theme Apply still needs
a live check with the latest bridge loaded. Display trials are session-only and
have independent timed restoration. This preview targets X11, not Wayland. Rotated/scaled display configurations may
be inspection-only. New Wi-Fi connections currently act as secondary connections
(no default route); enterprise/legacy security and advanced connection/VPN editing
use the companion connection editor. Pairing covers common devices but is not a
complete interactive Bluetooth passkey agent. Scanner management, advanced CUPS
driver setup and a full native advanced network editor remain future work.

Imported from control-centre revision `a3db78f`. Internal build infrastructure,
host snapshots and generated binaries are excluded from this checkout.

## License

Original code: GNU GPL version 3; see [LICENSE](LICENSE).
Original SVG artwork: CC BY-SA 4.0; see [ARTWORK.md](ARTWORK.md) and
[asset provenance](assets/provenance.json). Desktop themes are not bundled.

## Feedback and related projects

Please report reproducible issues at https://github.com/auzieman/E-control/issues
with your E/EFL version, Alpine version, affected section and steps to reproduce.
Remove passwords, access tokens and personal network/account details from logs.

- [AlpinEifyd](https://github.com/auzieman/AlpinEifyd)
- [E-Jamz](https://github.com/auzieman/E-Jamz)
- [BlackKnight E Theme](https://github.com/auzieman/BlackKnight-E-Theme)
