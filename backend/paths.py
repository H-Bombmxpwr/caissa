"""Keep personal data independent of the replaceable application folder."""
import os
import shutil
import sqlite3
import sys
import json
import tempfile
from contextlib import closing


def preferences_path():
    base = os.environ.get('APPDATA') or os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'Caissa', 'storage.json')


def storage_preferences():
    try:
        with open(preferences_path(), encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def save_storage_preferences(value):
    path = preferences_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def validate_destination(source, target):
    source, target = os.path.realpath(source), os.path.realpath(target)
    try:
        common = os.path.commonpath([source, target])
    except ValueError:  # Different Windows drives.
        common = None
    if common and os.path.normcase(common) in (os.path.normcase(source), os.path.normcase(target)):
        raise ValueError('Choose a folder outside your current library, not a parent of it.')
    if not os.path.isdir(target) or os.listdir(target):
        raise ValueError('Choose an empty folder. Existing files will not be overwritten.')
    # Detect unwritable destinations before saving the selection.
    with tempfile.TemporaryFile(dir=target):
        pass
    return source, target


def schedule_storage_change(source, target):
    source, target = validate_destination(source, target)
    prefs = storage_preferences()
    prefs['pending'] = {'source': source, 'target': target}
    prefs.pop('error', None)
    save_storage_preferences(prefs)
    return target


def apply_pending_storage(prefs):
    """Copy after the previous app has closed; switch only after a complete copy."""
    pending = prefs['pending']
    source, target = validate_destination(pending['source'], pending['target'])
    if not os.path.isfile(os.path.join(source, 'library.db')):
        raise ValueError('The original library is missing. Restore it before changing storage.')
    with tempfile.TemporaryDirectory(prefix='.caissa-copy-', dir=os.path.dirname(target)) as temporary:
        staged = os.path.join(temporary, 'library')
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns('library.db', 'library.db-wal', 'library.db-shm'))
        with closing(sqlite3.connect(os.path.join(source, 'library.db'))) as src:
            with closing(sqlite3.connect(os.path.join(staged, 'library.db'))) as dst:
                src.backup(dst)
        # rmdir only succeeds if the selected folder is still empty.
        os.rmdir(target)
        os.replace(staged, target)
    prefs = {'library_dir': target}
    save_storage_preferences(prefs)
    return target


def default_data_dir():
    if os.environ.get('DATA_DIR'):
        return os.path.abspath(os.path.expanduser(os.environ['DATA_DIR']))
    prefs = storage_preferences()
    if prefs.get('pending'):
        try:
            return apply_pending_storage(prefs)
        except (OSError, ValueError, sqlite3.Error) as err:
            prefs['error'] = str(err)
            save_storage_preferences(prefs)
            return prefs['pending']['source']
    if prefs.get('library_dir'):
        target = prefs['library_dir']
        if not os.path.isfile(os.path.join(target, 'library.db')):
            raise OSError('Your Caissa library is unavailable at '+target+'. Reconnect the drive and try again.')
        return target
    base = os.environ.get('APPDATA') or os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    target = os.path.join(base, 'Caissa', 'library')
    legacy = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'library')
    if not getattr(sys, 'frozen', False) and os.path.isfile(os.path.join(legacy, 'library.db')) and not os.path.exists(target):
        staging = target + '.migration'
        # Retain the original library. SQLite backup includes any WAL transactions.
        shutil.copytree(legacy, staging, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('library.db', 'library.db-wal', 'library.db-shm'))
        with closing(sqlite3.connect(os.path.join(legacy, 'library.db'))) as source:
            with closing(sqlite3.connect(os.path.join(staging, 'library.db'))) as dest:
                source.backup(dest)
        for suffix in ('-wal', '-shm'):
            sidecar = os.path.join(staging, 'library.db') + suffix
            if os.path.exists(sidecar):
                os.remove(sidecar)
        os.rename(staging, target)
    return target
