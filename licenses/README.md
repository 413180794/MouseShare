These unmodified upstream license texts supplement wheel metadata, which omits
some license files. `scripts/build.py` copies this directory into every installer.

- `Qt/`: https://github.com/qt/qtbase/tree/v6.10.3/LICENSES
  The complete license-text directory covers the license options and third-party
  notices referenced by Qt; MouseShare uses dynamically linked LGPL Qt modules.
- `PyObjC.txt`: https://github.com/ronaldoussoren/pyobjc/blob/v12.2.2/pyobjc-core/License.txt
- `Python.txt`: https://github.com/python/cpython/blob/v3.13.12/LICENSE

Dependency versions and their packaged license files are also included in each
application's `licenses` directory. Corresponding-source locations and library
replacement instructions are in `THIRD_PARTY.md`.
