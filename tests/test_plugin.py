import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import vdf
from playlite.providers import discover_plugins, installation_methods

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('steam_test_plugin', ROOT / 'plugin.py',
                                             submodule_search_locations=[str(ROOT)])
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from steam_test_plugin import library, runtime, detection


def write_vdf(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(vdf.dumps(data))


def manifest(root, identity='10', name='Example', directory='Example', flags='4'):
    (root / 'steamapps/common' / directory).mkdir(parents=True, exist_ok=True)
    write_vdf(root / f'steamapps/appmanifest_{identity}.acf', {'AppState': {
        'appid': identity, 'name': name, 'installdir': directory, 'StateFlags': flags}})


class LibraryTests(unittest.TestCase):
    def test_multiple_libraries_deduplication_metadata_and_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'Steam'
            extra = Path(temporary) / 'Other'
            manifest(root)
            manifest(extra)
            manifest(extra, '20', 'Second', 'Second')
            prefix = extra / 'steamapps/compatdata/20/pfx'
            prefix.mkdir(parents=True)
            write_vdf(root / 'steamapps/libraryfolders.vdf', {'libraryfolders': {
                '0': {'path': str(root)}, '1': {'path': str(extra)}}})
            games = library.import_games(root)
            self.assertEqual([g['SteamAppId'] for g in games], ['10', '20'])
            self.assertEqual(games[1]['Prefix'], str(prefix))
            self.assertEqual(games[0]['MetadataIds'], {'SteamMetadata': '10'})
            self.assertTrue(all(g['IsInstalled'] for g in games))

    def test_legacy_library_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, extra = Path(temporary) / 'Steam', Path(temporary) / 'Other'
            manifest(extra)
            write_vdf(root / 'steamapps/libraryfolders.vdf', {'libraryfolders': {'1': str(extra)}})
            self.assertEqual(len(library.import_games(root)), 1)

    def test_invalid_incomplete_and_tools_are_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest(root)
            manifest(root, '20', flags='2')
            manifest(root, '30', name='Proton 9.0')
            manifest(root, '40', directory='../escape')
            (root / 'steamapps/appmanifest_50.acf').write_text('malformed {')
            self.assertEqual([g['SteamAppId'] for g in library.import_games(root)], ['10'])

    def test_missing_client_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'Steam library not found'):
                library.import_games(Path(temporary))


class RuntimeTests(unittest.TestCase):
    def test_native_precedes_flatpak_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            native = home / '.local/share/Steam'
            flatpak = home / '.var/app/com.valvesoftware.Steam/data/Steam'
            (flatpak / 'steamapps').mkdir(parents=True)
            self.assertEqual(runtime.installation(home, home / '.local/share'), (flatpak, True))
            (native / 'steamapps').mkdir(parents=True)
            self.assertEqual(runtime.installation(home, home / '.local/share'), (native, False))

    def test_launch_commands_and_invalid_ids(self):
        with patch.object(runtime.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name):
            self.assertEqual(runtime.launch_command('10'), ['/usr/bin/steam', 'steam://rungameid/10'])
            self.assertEqual(runtime.launch_command('10', True), ['/usr/bin/flatpak', 'run', runtime.APP_ID, 'steam://rungameid/10'])
            for value in ('', '0', '-1', '１', '10;echo bad'):
                with self.assertRaises(ValueError):
                    runtime.launch_command(value)
        with patch.object(runtime.shutil, 'which', return_value=None):
            with self.assertRaises(ValueError):
                runtime.launch_command('10')


class IntegrationTests(unittest.TestCase):
    def provider(self):
        provider = module.Plugin()
        provider.id, provider.name, provider.version = 'SteamIntegration', 'Steam Integration', '1.0.0'
        return provider

    def test_discovery_and_installation_method(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / 'steam').symlink_to(ROOT, target_is_directory=True)
            providers = discover_plugins(temporary)
            self.assertIn('SteamIntegration', providers)
            self.assertIn('SteamImport', installation_methods(providers))

    def test_multiple_actions_detection_ignores_metadata_only(self):
        provider = self.provider()
        games = [{'Id': 'one', 'PlayActions': [{'Integration': provider.id, 'GameId': '10'},
                                              {'Integration': provider.id, 'GameId': '20'}]},
                 {'Id': 'metadata', 'MetadataIds': {'SteamMetadata': '20'}},
                 {'Id': 'legacy', 'GameProvider': provider.id, 'SteamAppId': '20'}]
        with patch('steam_test_plugin.detection.process_snapshot', return_value=[{'appid': '20'}]):
            self.assertEqual(provider.detect_running(games), {'one', 'legacy'})

    def test_proc_snapshot_filters_clients_zombies_and_foreign_users(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary)
            for pid, exe, state, identity in [('1', '/games/game', 'S', '10'),
                                              ('2', '/usr/bin/steam', 'S', '20'),
                                              ('3', '/games/game', 'Z', '30'),
                                              ('4', '/games/game', 'S', '0')]:
                entry = proc / pid
                entry.mkdir()
                (entry / 'stat').write_text(f'{pid} (game) {state} ' + '0 ' * 30)
                (entry / 'environ').write_bytes(f'SteamAppId={identity}\0'.encode())
                (entry / 'exe').symlink_to(exe)
            self.assertEqual(detection.process_snapshot(proc), [{'appid': '10', 'exe': '/games/game'}])
            with patch.object(detection.os, 'getuid', return_value=-1):
                self.assertEqual(detection.process_snapshot(proc), [])

    def test_editor_import_collect_and_method_switch(self):
        from PyQt6.QtWidgets import QApplication
        from playlite.add_game import AddGameEditor
        from playlite.play_actions import actions_for
        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            providers = {self.provider().id: self.provider()}
            with patch('playlite.providers.discover_plugins', return_value=providers):
                editor = AddGameEditor('', data, installation_method='SteamImport')
                selected = {'Name': 'Example', 'SteamAppId': '10', 'InstallDirectory': '/games/Example',
                            'Prefix': '', 'Source': 'Steam', 'IsInstalled': True}
                editor.installation_widget.selected = selected
                editor.apply_metadata(selected)
                editor.save()
                self.assertEqual(editor.result_game['PlayActions'][0]['GameId'], '10')
                self.assertEqual(editor.result_game['PlayActions'][0]['Name'], 'Play Example')
                self.assertEqual(editor.result_game['MetadataIds'], {'SteamMetadata': '10'})
                editor.installation_method.setCurrentIndex(editor.installation_method.findData('Manual'))
                self.assertEqual(editor.installation_plugin.id, 'Manual')
                editor.close()
                settings = self.provider().create_action_editor({})
                self.assertEqual(settings.collect(), {})
                settings.close()


class LibrarySettingsTests(unittest.TestCase):
    def test_manual_library_and_clear_restore_detection(self):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
            manual = root / 'manual'
            automatic = root / 'data/Steam'
            automatic.joinpath('steamapps').mkdir(parents=True)
            with patch('PyQt6.QtCore.QSettings', return_value=settings), \
                    patch.dict(os.environ, {'HOME': str(root), 'XDG_DATA_HOME': str(root / 'data'), 'PLAYLITE_PROFILE': ''}):
                plugin = module.Plugin()
                widget = plugin.create_settings()
                widget.library_folder.setText(str(manual))
                with self.assertRaises(ValueError):
                    plugin.save_settings(widget)
                manual.joinpath('steamapps').mkdir(parents=True)
                plugin.save_settings(widget)
                self.assertEqual(runtime.installation()[0], manual)
                widget.library_folder.clear()
                plugin.save_settings(widget)
                self.assertEqual(runtime.installation()[0], automatic)
                widget.deleteLater()
                app.processEvents()
