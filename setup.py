"""C-extension build for the vendored tree-sitter-rescript binding.

Pure-Python project metadata still lives in pyproject.toml; this file exists
only because setuptools' declarative TOML config does not support
`ext_modules`. Mirrors the upstream
rescript-lang/tree-sitter-rescript v6.0.0 setup.py with paths rewritten
to the vendored location.
"""
from sysconfig import get_config_var

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


_VENDOR = "graphify/_vendor/tree_sitter_rescript"


class BuildExt(build_ext):
    def build_extension(self, ext: Extension) -> None:
        if self.compiler.compiler_type != "msvc":
            ext.extra_compile_args = ["-std=c11", "-fvisibility=hidden"]
        else:
            ext.extra_compile_args = ["/std:c11", "/utf-8"]
        if ext.py_limited_api:
            ext.define_macros.append(("Py_LIMITED_API", "0x030A0000"))
        super().build_extension(ext)


setup(
    ext_modules=[
        Extension(
            name="graphify._vendor.tree_sitter_rescript._binding",
            sources=[
                f"{_VENDOR}/binding.c",
                f"{_VENDOR}/src/parser.c",
                f"{_VENDOR}/src/scanner.c",
            ],
            include_dirs=[f"{_VENDOR}/src"],
            define_macros=[
                ("PY_SSIZE_T_CLEAN", None),
                ("TREE_SITTER_HIDE_SYMBOLS", None),
            ],
            py_limited_api=not get_config_var("Py_GIL_DISABLED"),
        )
    ],
    cmdclass={"build_ext": BuildExt},
)
