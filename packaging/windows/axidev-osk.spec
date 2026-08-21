from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


repo_root = Path(SPECPATH).parents[1]
entrypoint = repo_root / "src" / "axidev_osk" / "__main__.py"
manifest = Path(SPECPATH) / "axidev-osk.manifest"

analysis = Analysis(
    [str(entrypoint)],
    pathex=[
        str(repo_root / "src"),
        str(repo_root / "vendor" / "axidev-io-python" / "src"),
    ],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("axidev_osk.components"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="axidev-osk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    manifest=str(manifest),
    uac_uiaccess=True,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="axidev-osk",
)
