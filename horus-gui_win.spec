# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import os
import sysconfig
from PyInstaller.utils.hooks import collect_data_files

scripts_dir = sysconfig.get_path("scripts")

binaries = [
    (os.path.join(scripts_dir, "rtlsdr.dll"), "."),
    (os.path.join(scripts_dir, "libusb-1.0.dll"), "."),
]

for dll_path, _ in binaries:
    if not os.path.isfile(dll_path):
        raise FileNotFoundError("DLL nao encontrada: " + dll_path)
a = Analysis(['horus-gui.py'],
             pathex=['.'],
             binaries=binaries,
             datas=collect_data_files("horusbinaryv3"),
             hiddenimports=['pkg_resources.py2_warn', '_cffi_backend'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='horus-gui',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True,
          icon='doc\\horus_icon.ico')
