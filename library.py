"""Read Steam's local library manifests without modifying client data."""
import logging
from pathlib import Path
import uuid
import vdf


def read_vdf(path):
    with path.open(encoding='utf-8', errors='replace') as stream:
        return vdf.load(stream)


def library_folders(root):
    folders = [Path(root).resolve()]
    path = Path(root) / 'steamapps/libraryfolders.vdf'
    if path.is_file():
        try:
            entries = read_vdf(path).get('libraryfolders', {})
            for key, value in entries.items():
                if not str(key).isdigit():
                    continue
                location = value.get('path') if isinstance(value, dict) else value
                if location and Path(location).is_absolute():
                    folder = Path(location).resolve()
                    if folder not in folders:
                        folders.append(folder)
        except (OSError, ValueError, SyntaxError, AttributeError) as error:
            logging.warning('Cannot read Steam library folders %s: %s', path, error)
    return folders


def import_games(root, provider_id='SteamIntegration'):
    if not (Path(root) / 'steamapps').is_dir():
        raise ValueError('Steam library not found. Open Steam and install a game first.')
    games = {}
    for library in library_folders(root):
        for manifest in sorted((library / 'steamapps').glob('appmanifest_*.acf')):
            try:
                data = read_vdf(manifest)['AppState']
                identity = str(data['appid'])
                if not identity.isascii() or not identity.isdigit() or int(identity) < 1:
                    raise ValueError('Invalid app ID')
                identity = str(int(identity))
                if manifest.name != f'appmanifest_{identity}.acf':
                    raise ValueError('App ID does not match manifest filename')
                name = data['name'].strip()
                relative = Path(data['installdir'])
                common = (library / 'steamapps/common').resolve()
                directory = (common / relative).resolve()
                if relative.is_absolute() or directory == common or not directory.is_relative_to(common):
                    raise ValueError('Invalid installation directory')
                if not name:
                    raise ValueError('Missing game name')
                # Client tools also have manifests; omit common runtime packages.
                if name.startswith(('Proton ', 'Steam Linux Runtime')) or identity == '228980':
                    continue
                installed = bool(int(data.get('StateFlags', '0')) & 4) and directory.is_dir()
                if not installed:
                    continue
                prefix = library / 'steamapps/compatdata' / identity / 'pfx'
                games.setdefault(identity, {
                    'Id': str(uuid.uuid4()), 'Name': name, 'GameProvider': provider_id,
                    'SteamAppId': identity, 'MetadataIds': {'SteamMetadata': identity},
                    'InstallDirectory': str(directory), 'Prefix': str(prefix) if prefix.is_dir() else '',
                    'Source': 'Steam', 'IsInstalled': True,
                })
            except (OSError, ValueError, SyntaxError, KeyError, TypeError, AttributeError) as error:
                logging.warning('Skipping Steam manifest %s: %s', manifest, error)
    return sorted(games.values(), key=lambda game: game['Name'].casefold())
