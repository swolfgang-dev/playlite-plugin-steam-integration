import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('steam_executables',Path(__file__).resolve().parents[1]/'executables.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def exe(path,mono=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    data=bytearray(128);data[:2]=b'MZ';struct.pack_into('<I',data,60,64);data[64:68]=b'PE\0\0';struct.pack_into('<H',data,68,0x8664);path.write_bytes(data)
    if mono:
        managed=path.with_name(path.stem+'_Data')/'Managed';managed.mkdir(parents=True);(managed/'Assembly-CSharp.dll').touch()


class ExecutableTests(unittest.TestCase):
    def test_prefers_mono_and_keeps_multiple_choices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);exe(root/'Launcher.exe');exe(root/'UnityCrashHandler64.exe')
            exe(root/'nested/Game.exe',True)
            self.assertEqual(module.candidates(root),[str(root/'nested/Game.exe')])
            exe(root/'Other.exe',True)
            self.assertEqual(len(module.candidates(root)),2)

    def test_ignores_invalid_and_external_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);game=root/'game';game.mkdir();exe(root/'outside/Game.exe',True)
            (game/'bad.exe').write_bytes(b'not PE');(game/'linked').symlink_to(root/'outside',target_is_directory=True)
            self.assertEqual(module.candidates(game),[])
