from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


repo_root = Path(SPECPATH).parents[1]
entrypoint = repo_root / "src" / "axidev_osk" / "__main__.py"
manifest = Path(SPECPATH) / "axidev-osk.manifest"
icon_directory = repo_root / "src" / "axidev_osk" / "assets"
icon_svg = icon_directory / "axidev-osk.svg"
icon_ico = icon_directory / "axidev-osk.ico"
resources_dll = Path(SPECPATH) / "axidev-osk-resources.dll"

analysis = Analysis(
    [str(entrypoint)],
    pathex=[
        str(repo_root / "src"),
        str(repo_root / "vendor" / "axidev-io-python" / "src"),
    ],
    binaries=[],
    datas=[
        (str(icon_svg), "axidev_osk/assets"),
        (str(icon_ico), "axidev_osk/assets"),
        (str(resources_dll), "."),
    ],
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
    icon=str(icon_ico),
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
