"""Find local Windows launch candidates without guessing between executables."""
import os
from pathlib import Path
import struct


def candidates(directory):
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        return []
    found, mono = [], []
    for index, (folder, directories, files) in enumerate(os.walk(root, followlinks=False)):
        if index >= 500:
            break
        folder = Path(folder)
        directories[:] = sorted(name for name in directories if not (folder/name).is_symlink()
                                and name.casefold() not in ('bepinex', 'redist', '_commonredist')
                                and len(folder.relative_to(root).parts) < 4)
        for name in sorted(files):
            path = folder/name
            if path.suffix.casefold() != '.exe' or path.is_symlink():
                continue
            if any(word in path.stem.casefold() for word in ('crashhandler', 'uninstall', 'vcredist', 'dxsetup')):
                continue
            try:
                with path.open('rb') as stream:
                    if stream.read(2) != b'MZ':continue
                    stream.seek(60);offset=stream.read(4)
                    if len(offset)!=4:continue
                    stream.seek(struct.unpack('<I',offset)[0]);header=stream.read(6)
                    if len(header)!=6 or header[:4]!=b'PE\0\0' or struct.unpack('<H',header[4:])[0] not in (0x14c,0x8664):continue
            except OSError:
                continue
            found.append(str(path))
            if (folder/(path.stem+'_Data')/'Managed'/'Assembly-CSharp.dll').is_file() and not (folder/'GameAssembly.dll').exists():
                mono.append(str(path))
    return sorted(mono or found, key=str.casefold)
