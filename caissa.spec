# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Caissa. Build with: .\build.ps1
import os

ROOT = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(ROOT, 'index.html'), '.'),
    (os.path.join(ROOT, 'css'), 'css'),
    (os.path.join(ROOT, 'js'), 'js'),
    (os.path.join(ROOT, 'data'), 'data'),
    (os.path.join(ROOT, 'assets'), 'assets'),
    (os.path.join(ROOT, 'vendor', 'stockfish'), os.path.join('vendor', 'stockfish')),
]

a = Analysis(
    ['desktop.py'],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=['backend.api', 'backend.store', 'backend.engine', 'backend.lichess', 'server'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc_data'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Caissa',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(ROOT, 'assets', 'caissa.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Caissa',
)
