"""Detect app sessions from process environments, independently of client lifetime."""
import os
from pathlib import Path

CLIENT_PROCESSES = {'steam', 'steamwebhelper', 'steamservice', 'steam-runtime-launcher-service',
                    'wineserver', 'services.exe', 'winedevice.exe', 'explorer.exe', 'rpcss.exe'}


def process_snapshot(proc=Path('/proc')):
    records = []
    try:
        entries = list(proc.iterdir())
    except OSError:
        return records
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            stat = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            if stat[0] == 'Z':
                continue
            env = dict(value.split('=', 1) for value in (entry / 'environ').read_bytes().decode(
                errors='replace').split('\0') if '=' in value)
            identity = env.get('SteamAppId') or env.get('SteamGameId') or env.get('STEAM_COMPAT_APP_ID')
            if not identity or not identity.isascii() or not identity.isdigit() or int(identity) < 1:
                continue
            executable = os.readlink(entry / 'exe')
            if Path(executable).name.casefold() in CLIENT_PROCESSES:
                continue
            records.append({'pid': int(entry.name), 'start': stat[19], 'appid': str(int(identity)), 'exe': executable})
        except (OSError, ValueError, IndexError):
            continue
    return records


def detect_running(games, records):
    running = {record['appid'] for record in records}
    return {game['Id'] for game in games if str(game.get('SteamAppId') or '') in running}
