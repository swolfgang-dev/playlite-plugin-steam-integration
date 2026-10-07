import subprocess
from playlite.providers import IntegrationPlugin
from . import runtime


class Plugin(IntegrationPlugin):
    action_id_field = 'SteamAppId'
    settings_group = 'installation'

    def association_id(self, game):
        return game.get('SteamAppId')

    def owns(self, game):
        if 'PlayActions' in game:
            return any(action.get('Integration') == self.id for action in game['PlayActions'] or [])
        if 'GameProvider' in game:
            return game.get('GameProvider') == self.id
        return bool(game.get('SteamAppId'))

    def validate_action(self, action):
        identity = str(action.get('GameId') or '')
        if not identity.isascii() or not identity.isdigit() or int(identity) < 1:
            raise ValueError('Steam play actions need a positive numeric app ID.')

    def launch(self, game):
        _, flatpak = runtime.installation()
        return subprocess.Popen(runtime.launch_command(game.get('SteamAppId'), flatpak), start_new_session=True, env=runtime.environment())

    def import_games(self):
        from .library import import_games
        root, _ = runtime.installation()
        return import_games(root, self.id)

    def installation_methods(self):
        from .import_games import Plugin as Import
        method = Import()
        method.id, method.name, method.type = 'SteamImport', 'Import from Steam', 'installation'
        method.version = self.version
        return [method]

    def detect_running(self, games):
        from playlite.play_actions import actions_for, action_game
        from .detection import detect_running, process_snapshot
        resolved = [action_game(game, action, self) for game in games if self.owns(game)
                    for action in actions_for(game, [self]) if action.get('Integration') == self.id]
        return detect_running(resolved, process_snapshot()) if resolved else set()

    def stop(self, game):
        from playlite.play_actions import actions_for, action_game
        from playlite.process_control import terminate_processes
        from .detection import process_snapshot
        identities = {str(action_game(game, action, self).get('SteamAppId'))
                      for action in actions_for(game, [self]) if action.get('Integration') == self.id}
        return terminate_processes(record for record in process_snapshot() if record['appid'] in identities)

    def create_action_editor(self, action, parent=None):
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
        class Settings(QWidget):
            def collect(self):
                return {}
        widget = Settings(parent)
        layout = QVBoxLayout(widget)
        label = QLabel('Steam manages the executable, Proton version, and launch options. Set launch options in Steam’s game properties.')
        label.setWordWrap(True)
        layout.addWidget(label)
        return widget

    def create_settings(self, parent=None):
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
        from PyQt6.QtCore import QSettings
        from playlite.lifecycle import choose_directory
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        root, flatpak = runtime.installation()
        label = QLabel(f'Imports installed games from all local Steam library folders.\nClient: {"Flatpak" if flatpak else "Native"}\nLibrary: {root}\nNo Steam API key is required.')
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(QLabel('Steam library folder'))
        widget.library_folder = QLineEdit(QSettings('Playlite', 'Steam').value('LibraryDirectory', '', type=str))
        widget.library_folder.setPlaceholderText(str(root) + ' (automatic when empty)')
        row = QHBoxLayout()
        row.addWidget(widget.library_folder)
        browse = QPushButton('Browse…')
        def select():
            folder = choose_directory(widget, 'Steam library folder', widget.library_folder.text() or str(root))
            if folder:
                widget.library_folder.setText(folder)
        browse.clicked.connect(select)
        row.addWidget(browse)
        layout.addLayout(row)
        hint = QLabel('Leave empty for automatic detection. Choose the folder containing steamapps; its additional libraries are also imported.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        return widget

    def save_settings(self, widget):
        from pathlib import Path
        from PyQt6.QtCore import QSettings
        value = widget.library_folder.text().strip()
        if value and (not Path(value).is_absolute() or not (Path(value) / 'steamapps').is_dir()):
            raise ValueError('Choose an absolute Steam library folder containing steamapps.')
        settings = QSettings('Playlite', 'Steam')
        settings.setValue('LibraryDirectory', value)
        settings.sync()
