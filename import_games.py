"""Single-game import in the Add Game editor, matching other integrations."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QVBoxLayout, QPushButton, QDialog, QLineEdit,
                             QListWidget, QListWidgetItem, QDialogButtonBox, QLabel)
from playlite.providers import InstallationPlugin, discover_plugins
from playlite.lifecycle import run_dialog, show_warning


class Plugin(InstallationPlugin):
    description = 'Select an installed Steam game to link it to Playlite.'
    cli_name = 'import-steam'

    def create_editor(self, editor, game):
        from playlite.manual_installation import ManualInstallation
        self.manual = ManualInstallation()
        widget = self.manual.create_editor(editor, game, field_keys=('InstallDirectory', 'SteamId'))
        widget.selected = dict(game) if game.get('SteamAppId') else None
        layout = widget.layout()
        widget.summary = QLabel(game.get('Name', '') if widget.selected else 'No Steam game selected')
        layout.addRow('', widget.summary)
        button = QPushButton('Import from Steam…')
        widget.import_button = button
        layout.addRow('', button)
        button.clicked.connect(lambda: self.choose_game(widget, editor))
        return widget

    def choose_game(self, widget, editor):
        try:
            provider = discover_plugins()['SteamIntegration']
            games = provider.import_games()
            from playlite.play_actions import actions_for
            known = {str(action.get('GameId') or game.get('SteamAppId') or '')
                     for game in getattr(editor.parent(), 'games', [])
                     for action in actions_for(game, [provider])
                     if action.get('Integration') == provider.id}
            dialog = QDialog(editor)
            dialog.setWindowTitle('Import from Steam')
            dialog.resize(480, 520)
            layout = QVBoxLayout(dialog)
            search = QLineEdit()
            search.setPlaceholderText('Search games')
            layout.addWidget(search)
            choices = QListWidget()
            layout.addWidget(choices)
            for game in games:
                if game['SteamAppId'] in known:
                    continue
                item = QListWidgetItem(f"{game['Name']} — {game['SteamAppId']}")
                item.setData(Qt.ItemDataRole.UserRole, game)
                choices.addItem(item)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
            select = buttons.addButton('Import selected', QDialogButtonBox.ButtonRole.AcceptRole)
            select.setEnabled(False)
            def update(*_):
                item = choices.currentItem()
                select.setEnabled(item is not None and not item.isHidden())
            def filter_games(query):
                for index in range(choices.count()):
                    item = choices.item(index)
                    item.setHidden(query.casefold() not in item.text().casefold())
                update()
            search.textChanged.connect(filter_games)
            choices.currentItemChanged.connect(update)
            select.clicked.connect(dialog.accept)
            choices.itemDoubleClicked.connect(lambda *_: dialog.accept())
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if run_dialog(dialog) != QDialog.DialogCode.Accepted:
                return
            item = choices.currentItem()
            if item is None or item.isHidden():
                return
            widget.selected = item.data(Qt.ItemDataRole.UserRole)
            editor.apply_metadata({key: value for key, value in widget.selected.items() if key != 'Id'})
            widget.summary.setText(widget.selected['Name'])
            editor.flags['IsInstalled'].setChecked(True)
        except Exception as error:
            show_warning(editor, 'Cannot import from Steam', str(error))

    def collect(self, widget, game):
        if not widget.selected:
            raise ValueError('Select a Steam game first.')
        game = self.manual.collect(widget, game)
        for key in ('SteamAppId', 'Prefix', 'Source', 'IsInstalled'):
            game[key] = widget.selected[key]
        ids = dict(game.get('MetadataIds') or {})
        ids['SteamMetadata'] = game['SteamAppId']
        game.update(MetadataIds=ids, GameProvider='SteamIntegration', InstallationMethod=self.id)
        return game

    def configure_cli(self, parser):
        parser.add_argument('--steam-id', type=int, required=True)

    def cli_game(self, args, plugins):
        game = next((game for game in plugins['SteamIntegration'].import_games()
                     if game['SteamAppId'] == str(args.steam_id)), None)
        if game is None:
            raise ValueError('Installed Steam app ID not found.')
        game['InstallationMethod'] = self.id
        return game
