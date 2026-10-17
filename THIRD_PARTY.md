MouseShare code is MIT licensed. Bundled dependencies retain their own licenses.
Installers include a `licenses` directory with dependency metadata and license texts.

* PySide6 Essentials / Qt 6.10.3: LGPLv3 (applicable Qt modules) / GPL / commercial options.
  MouseShare uses the LGPL distribution, dynamically linked. You may replace the Qt/PySide6
  libraries in the application bundle (`_internal` on Windows, `Contents/Frameworks` on macOS).
  Rebuilding this MIT application is permitted; reverse engineering for debugging modifications
  to LGPL components is permitted under their license. A modified macOS bundle requires ad-hoc
  re-signing with `codesign --force --deep --sign - MouseShare.app`.
  Corresponding upstream source: https://download.qt.io/official_releases/qt/6.10/6.10.3/submodules/
  and https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.3-src/
  License: https://www.gnu.org/licenses/lgpl-3.0.html
* cryptography: Apache-2.0 OR BSD-3-Clause; includes OpenSSL, whose license is bundled.
  Source: https://github.com/pyca/cryptography/tree/46.0.7
* PyObjC (macOS): MIT. Source: https://github.com/ronaldoussoren/pyobjc
* Python: PSF license. Source: https://www.python.org/downloads/source/
* PyInstaller bootloader: GPL with the bootloader exception allowing bundled applications.
  Source: https://github.com/pyinstaller/pyinstaller

