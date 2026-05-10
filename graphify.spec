# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all skill files
datas = [('graphify/*.md', 'graphify')]

# List of tree-sitter packages to include
ts_packages = [
    'tree_sitter',
    'tree_sitter_python', 'tree_sitter_javascript', 'tree_sitter_typescript',
    'tree_sitter_go', 'tree_sitter_rust', 'tree_sitter_java', 'tree_sitter_groovy',
    'tree_sitter_c', 'tree_sitter_cpp', 'tree_sitter_ruby', 'tree_sitter_c_sharp',
    'tree_sitter_kotlin', 'tree_sitter_scala', 'tree_sitter_php', 'tree_sitter_swift',
    'tree_sitter_lua', 'tree_sitter_zig', 'tree_sitter_powershell', 'tree_sitter_elixir',
    'tree_sitter_objc', 'tree_sitter_julia', 'tree_sitter_verilog', 'tree_sitter_fortran',
    'tree_sitter_sql'
]

# Additional packages that need data files bundled
extra_packages = [
    'graspologic', 'networkx', 'matplotlib', 'datasketch', 'rapidfuzz',
    'pypdf', 'docx', 'openpyxl'
]

hiddenimports = [
    'networkx', 'datasketch', 'rapidfuzz', 'pypdf', 'markdownify', 
    'watchdog', 'graspologic', 'docx', 'openpyxl', 'faster_whisper', 
    'yt_dlp', 'matplotlib', 'openai', 'tiktoken', 'boto3', 'mcp'
]

for pkg in ts_packages + extra_packages:
    try:
        datas += collect_data_files(pkg)
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

a = Analysis(
    ['graphify/__main__.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Disable UPX on non-Windows due to compatibility issues
is_win = sys.platform.startswith('win')

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='graphify',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=is_win,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
