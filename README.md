# Steam Integration for Playlite

Import installed Steam games, launch through Steam, and detect game sessions for
Playlite's playtime tracking. Requires Playlite 0.2.41 or later, plugin API 1.

## Use

Install the plugin folder into `$XDG_DATA_HOME/playlite/plugins/playlite-plugin-steam-integration`
(default: `~/.local/share/playlite/plugins/playlite-plugin-steam-integration`), install the
`vdf>=3.4` Python dependency in Playlite's environment, and restart Playlite.
Once this repository has a public release, it can also be installed with:

```sh
playlite-plugins install swolfgang-dev/playlite-plugin-steam-integration
```

Choose **Add Game → Import from Steam**, search the installed library, select a
game, then save. Games already associated with a Steam play action are omitted.
The import records the app ID, installation folder, existing Proton prefix, and
Steam metadata ID. Steam Metadata and SteamGridDB can be installed alongside it.

The CLI installation method is `import-steam` with `--steam-id <appid>`.
For an existing Playlite entry, add a Steam Integration play action and enter its
numeric Steam app ID. Steam controls the executable, Proton selection, and launch
options; configure those in Steam's game properties.

## Discovery and tracking

Native Steam is preferred when its library exists. Otherwise, the plugin detects
Steam Flatpak (`com.valvesoftware.Steam`). It reads `libraryfolders.vdf` and each
library's `appmanifest_*.acf`, supporting both older and current library-folder
formats. Only fully installed entries with an existing installation directory
are offered. Malformed individual manifests are skipped with a log warning.
Common Proton/runtime packages and Steamworks redistributables are omitted;
other installed software may appear because app manifests do not identify types.

Detection scans the current user's Linux processes for Steam app environment IDs,
ignoring zombies, Steam client processes, and common persistent Wine services.
Playlite records the detected session duration. Games that remove those environment
variables, inaccessible processes, or games running on another device cannot be
tracked. Historical Steam playtime is not imported. Native and Flatpak discovery
share the same client selection used for launch.

No API key or network connection is needed to read the local library. This version
does not import uninstalled owned games or non-Steam shortcuts, create Steam
registrations, or uninstall games. Removing a Playlite entry leaves Steam intact.

## Development and releases

With Playlite and `vdf` installed in the active Python environment:

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
python3 tools/build_release.py
```

The build creates `dist/plugin.zip` and `dist/SHA256SUMS`, with `manifest.json` and
`plugin.py` at the archive root. Push a tag matching the manifest version, such as
`v1.0.0`, to run tests and publish a GitHub release. The standalone plugin archive
does not contain Playlite, tests, tools, or CI files.
