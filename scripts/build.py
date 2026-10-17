"""Build a self-contained app on the current OS. CI runs this on each target architecture."""
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ASSETS = ROOT / "build/icons"


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def make_icons():
    ASSETS.mkdir(parents=True, exist_ok=True)
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(8, 8)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#16233c"))
    p.drawRoundedRect(0, 0, 128, 128, 28, 28)
    p.setBrush(QColor("#59d8bb"))
    p.drawRoundedRect(15, 28, 44, 48, 6, 6)
    p.setBrush(QColor("#87b7ff"))
    p.drawRoundedRect(69, 49, 44, 48, 6, 6)
    p.setPen(QPen(QColor("white"), 5))
    p.drawLine(45, 92, 83, 31)
    p.drawLine(83, 31, 64, 38)
    p.drawLine(83, 31, 86, 51)
    p.end()
    png = ASSETS / "icon.png"
    image.scaled(256, 256).save(str(png))
    data = png.read_bytes()
    # Windows Vista+ supports PNG-compressed ICO images.
    ico = ASSETS / "MouseShare.ico"
    ico.write_bytes(struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32,
                                                            len(data), 22) + data)
    if sys.platform == "darwin":
        iconset = ASSETS / "MouseShare.iconset"
        iconset.mkdir(exist_ok=True)
        for size in [16, 32, 128, 256, 512]:
            image.scaled(size, size).save(str(iconset / f"icon_{size}x{size}.png"))
            image.scaled(size * 2, size * 2).save(str(iconset / f"icon_{size}x{size}@2x.png"))
        run("iconutil", "-c", "icns", iconset, "-o", ASSETS / "MouseShare.icns")


def licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    report = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        if name.lower() in {"mouseshare", "pytest", "ruff", "pyinstaller", "setuptools", "pip"}:
            continue
        report.append({"name": name, "version": dist.version,
                       "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", ""),
                       "home": dist.metadata.get("Home-page", "")})
        for file in dist.files or []:
            if any(part.lower().startswith(("license", "copying", "copyright")) for part in file.parts):
                source = dist.locate_file(file)
                if source.is_file():
                    target = destination / name / Path(file).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    (destination / "dependencies.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name in ["LICENSE", "THIRD_PARTY.md"]:
        shutil.copyfile(ROOT / name, destination / name)


def main():
    os.chdir(ROOT)
    make_icons()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
               "--name", "MouseShare", "--noupx", "--exclude-module", "tkinter",
               "--exclude-module", "unittest", "--icon", str(ASSETS / (
                   "MouseShare.icns" if sys.platform == "darwin" else "MouseShare.ico")),
               "--collect-submodules", "mouseshare"]
    if sys.platform == "darwin":
        command += ["--osx-bundle-identifier", "io.github.makesail.mouseshare",
                    "--hidden-import", "ApplicationServices", "--hidden-import", "CoreFoundation"]
    command += [str(ROOT / "launcher.py")]
    run(*command)
    if sys.platform == "darwin":
        bundle = DIST / "MouseShare.app"
        import plistlib
        info = bundle / "Contents/Info.plist"
        content = plistlib.loads(info.read_bytes())
        content.update({"CFBundleShortVersionString": "0.1.0", "CFBundleVersion": "1",
                        "LSMinimumSystemVersion": "13.0",
                        "NSLocalNetworkUsageDescription": "自动发现局域网中的电脑，并共享鼠标和键盘。",
                        "NSInputMonitoringUsageDescription": "读取键鼠输入以在您配对的电脑之间切换控制。",
                        "NSHighResolutionCapable": True})
        info.write_bytes(plistlib.dumps(content))
        licenses(bundle / "Contents/Resources/licenses")
        run("codesign", "--force", "--deep", "--sign", "-", bundle)
        run("codesign", "--verify", "--deep", "--strict", bundle)
        run(bundle / "Contents/MacOS/MouseShare", "--smoke-test")
        stage = ROOT / "build/dmg"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        shutil.copytree(bundle, stage / bundle.name, symlinks=True)
        (stage / "Applications").symlink_to("/Applications")
        shutil.copyfile(ROOT / "docs/INSTALL-macOS.txt", stage / "安装说明.txt")
        target = DIST / f"MouseShare-0.1.0-macOS-{platform.machine()}.dmg"
        target.unlink(missing_ok=True)
        run("hdiutil", "create", "-volname", "MouseShare", "-srcfolder", stage,
            "-ov", "-format", "UDZO", target)
    elif sys.platform == "win32":
        licenses(DIST / "MouseShare/licenses")
        run(DIST / "MouseShare/MouseShare.exe", "--smoke-test")
        compiler = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
        run(compiler, ROOT / "packaging/windows.iss")
        shutil.copyfile(ROOT / "docs/INSTALL-Windows.txt", DIST / "MouseShare/安装说明.txt")
        shutil.make_archive(str(DIST / "MouseShare-0.1.0-Windows-x64-portable"), "zip",
                            DIST, "MouseShare")
    else:
        raise RuntimeError("Build on Windows or macOS")


if __name__ == "__main__":
    main()

