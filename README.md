# E-control

A native Enlightenment/EFL workstation control panel, developed for AlpinEifyd
on Alpine Linux and X11. It follows the active desktop theme and brings common
settings into a sidebar with focused forms.

This is an initial preview. Audio, guarded display trials, NetworkManager
connections, BlueZ devices, appearance, accounts, services and system information
have provider integrations. Storage shows usage and volumes, with file browsing
and a GParted handoff. Some advanced settings still open Enlightenment dialogs;
printing remains an unfinished integration.

## Build and run

Requires a C compiler, pkg-config, Elementary/EFL development files, Edje tools,
GLib development files and Python 3. Runtime integrations use Python D-Bus,
NetworkManager, BlueZ, Pulse-compatible pactl, XRandR, OpenRC, util-linux and
optional firewalld. Missing services do not get enabled automatically.

```sh
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

## Validation and limitations

76 Python tests passed for the imported revision. The native Alpine build was
visually checked on the active desktop theme. Automated write tests use fixtures;
that does not establish every operation on every host. Theme Apply still needs
a live check with the latest bridge loaded. Display trials are session-only and
have independent timed restoration. This preview targets X11, not Wayland.

Imported from control-centre revision `a3db78f`. Internal build infrastructure,
host snapshots and generated binaries are excluded from this checkout.

## License

Original code: GNU GPL version 3; see [LICENSE](LICENSE).
Original SVG artwork: CC BY-SA 4.0; see [ARTWORK.md](ARTWORK.md) and
[asset provenance](assets/provenance.json). Desktop themes are not bundled.
