# -*- mode: python ; coding: utf-8 -*-
#
# Checked-in PyInstaller build spec (Phase 10) — run with:
#   pyinstaller TaskPlanner.spec
# from the repo root. Onedir build (not onefile): a Qt app's onefile
# re-extracts everything to a temp dir on every launch, which is a
# noticeably slower startup than onedir for no real portability benefit
# here. Produces dist/TaskPlanner/TaskPlanner.exe + its _internal/ deps.
#
# default_db_path() (app/database/db.py) resolves %APPDATA%/TaskPlanner/
# via os.environ only — no dependency on sys.executable/__file__, so it
# behaves identically frozen or not. Verified empirically, not just by
# reading the code: built this spec, ran the frozen exe, and confirmed
# it created/read the same %APPDATA%/TaskPlanner/task_planner.db as the
# unfrozen `python -m app.main` dev run (a task written by one was
# visible to the other).

a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TaskPlanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TaskPlanner',
)
