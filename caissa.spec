# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Caissa. Build with: .\build.ps1
import os

import sys

ROOT = os.path.abspath(SPECPATH)

# PyInstaller cannot cross-compile: each platform's build runs on that platform, and
# only the icon format differs. A missing icon is not worth failing a build over.
_icon = os.path.join(ROOT, 'assets', 'caissa.icns' if sys.platform == 'darwin'
                     else 'caissa.ico' if sys.platform == 'win32' else 'caissa.png')
ICON = _icon if os.path.exists(_icon) else None

datas = [
    (os.path.join(ROOT, 'index.html'), '.'),
    (os.path.join(ROOT, 'css'), 'css'),
    (os.path.join(ROOT, 'js'), 'js'),
    (os.path.join(ROOT, 'data'), 'data'),
    (os.path.join(ROOT, 'assets'), 'assets'),
    (os.path.join(ROOT, 'vendor', 'stockfish'), os.path.join('vendor', 'stockfish')),
]

# chess.com's sounds may sit in assets/sound/chesscom on the machine doing the build.
# They are proprietary: they are fetched for personal use and must not be shipped in a
# build any more than they are committed to the repository.
def _drop_chesscom(entries):
    blocked = os.path.join('assets', 'sound', 'chesscom')
    return [item for item in entries if blocked not in os.path.normpath(item[0])]


a = Analysis(
    [os.path.join(ROOT, 'desktop.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=['backend.api', 'backend.store', 'backend.engine', 'backend.lichess', 'server'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc_data'],
    noarchive=False,
)
a.datas = _drop_chesscom(a.datas)
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
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Caissa',
)

# macOS expects an .app bundle, and BUNDLE wraps the collected folder — not a second
# EXE. The other platforms ship the folder as it is.
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Caissa.app',
        icon=ICON,
        bundle_identifier='org.caissa.workbench',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '11.0',
            'CFBundleShortVersionString': '1.0.3',
        },
    )

# Windows: a build that arrives as a downloaded .zip carries the mark of the web on
# every file Explorer extracts, which puts them in the internet zone. .NET Framework
# then refuses to load pywebview's bundled Python.Runtime.dll from that zone, so the
# window never opens and the app dies during startup with
#     Failed to resolve Python.Runtime.Loader.Initialize
# The assemblies being refused are the ones shipped inside this very bundle, so opting
# them back into full trust is the whole fix. The file has to sit next to the .exe,
# which is not where COLLECT puts datas, so it is written here once the folder exists.
if sys.platform == 'win32':
    with open(os.path.join(DISTPATH, 'Caissa', 'Caissa.exe.config'), 'w',
              encoding='utf-8') as handle:
        handle.write(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<configuration>\n'
            '  <runtime>\n'
            '    <loadFromRemoteSources enabled="true" />\n'
            '  </runtime>\n'
            '</configuration>\n'
        )
