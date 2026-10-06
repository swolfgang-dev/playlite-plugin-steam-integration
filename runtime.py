"""Resolve one Steam client consistently for discovery and launching."""
import os
from pathlib import Path
import shutil
import pwd

APP_ID = 'com.valvesoftware.Steam'


def environment():
    """Lutris belongs to the desktop user, outside Playlite's private profile."""
    env = dict(os.environ)
    if env.get('PLAYLITE_PROFILE') == 'repo':
        env['HOME'] = env.get('PLAYLITE_HOST_HOME') or pwd.getpwuid(os.getuid()).pw_dir
        for name in ('DATA', 'CONFIG', 'CACHE', 'STATE'):
            variable = f'XDG_{name}_HOME'
            saved = env.get(f'PLAYLITE_HOST_{variable}')
            if saved:
                env[variable] = saved
            else:
                env.pop(variable, None)
    return env



def installation(home=None, data_home=None):
    use_override = home is None and data_home is None
    env = environment()
    home = Path(home or env.get('HOME') or Path.home())
    data = Path(data_home or env.get('XDG_DATA_HOME') or str(home / '.local/share'))
    candidates = [data / 'Steam', home / '.steam/steam', home / '.steam/root',
                  home / '.var/app' / APP_ID / 'data/Steam',
                  home / '.var/app' / APP_ID / '.local/share/Steam']
    if use_override:
        from PyQt6.QtCore import QSettings
        selected = QSettings('Playlite', 'Steam').value('LibraryDirectory', '', type=str).strip()
        if selected:
            root = Path(selected).expanduser()
            return root, APP_ID in root.parts or next((i >= 3 for i, candidate in enumerate(candidates) if (candidate / 'steamapps').is_dir()), False)
    for index, root in enumerate(candidates):
        if (root / 'steamapps').is_dir():
            return root.resolve(), index >= 3
    return candidates[0], False


def launch_command(app_id, flatpak=False):
    identity = str(app_id or '')
    if not identity.isascii() or not identity.isdigit() or int(identity) < 1:
        raise ValueError('Set a positive numeric Steam app ID.')
    executable = shutil.which('flatpak' if flatpak else 'steam')
    if not executable:
        raise ValueError('Install Steam to launch this game.' if not flatpak else 'Flatpak is not installed.')
    uri = 'steam://rungameid/' + str(int(identity))
    return [executable, 'run', APP_ID, uri] if flatpak else [executable, uri]
