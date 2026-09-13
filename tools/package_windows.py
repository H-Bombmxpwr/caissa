"""Package an already built Windows folder, preserving all runtime dependencies."""
from pathlib import Path
import hashlib
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    folder=ROOT/'dist/Caissa'
    required=['Caissa.exe','_internal/index.html','_internal/js/computer.js',
              '_internal/js/autocomplete.js','_internal/css/polish.css',
              '_internal/vendor/stockfish/stockfish.exe']
    for name in required:
        if not (folder/name).is_file():
            raise SystemExit('Build first: missing '+name)
    output=ROOT/'dist/Caissa-windows-x64.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(folder.rglob('*')):
            if not file.is_file():continue
            if file.name=='.env' or file.name.startswith('.env.'):
                raise SystemExit('Environment files must not be distributed')
            archive.write(file,file.relative_to(folder.parent))
    with zipfile.ZipFile(output) as archive:
        bad=archive.testzip()
        if bad:raise SystemExit('Corrupt archive member: '+bad)
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(digest+'  '+output.name+'\n',encoding='ascii')
    print(str(output))
    print(str(round(output.stat().st_size/1048576,1))+' MB; archive verified; SHA-256 '+digest)

if __name__=='__main__':main()
