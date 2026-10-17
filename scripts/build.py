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


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ASSETS = ROOT / "build/icons"


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def make_icons():
    ASSETS.mkdir(parents=True, exist_ok=True)
    # One source of artwork for the running app and all installer formats.
    sys.path.insert(0, str(ROOT))
    from mouseshare.branding import icon_image
    # Render every size from the vector source; small sizes use simplified artwork.
    images = {}
    for size in [16, 24, 32, 48, 64, 128, 256, 512, 1024]:
        images[size] = ASSETS / f"icon-{size}.png"
        icon_image(size).save(str(images[size]))
    shutil.copyfile(images[256], ASSETS / "icon.png")
    # Windows Vista+ supports PNG-compressed ICO images; include each shell size.
    entries = [(size, images[size].read_bytes()) for size in [16, 24, 32, 48, 64, 128, 256]]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    for size, data in entries:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    (ASSETS / "MouseShare.ico").write_bytes(header + directory + b"".join(data for _, data in entries))
    if sys.platform == "darwin":
        iconset = ASSETS / "MouseShare.iconset"
        iconset.mkdir(exist_ok=True)
        for size in [16, 32, 128, 256, 512]:
            shutil.copyfile(images[size], iconset / f"icon_{size}x{size}.png")
            shutil.copyfile(images[size * 2], iconset / f"icon_{size}x{size}@2x.png")
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
            if (file.name.lower().startswith(("license", "copying", "copyright"))
                    and file.suffix.lower() not in {".so", ".dll", ".py", ".yml", ".plist"}):
                source = dist.locate_file(file)
                if source.is_file():
                    target = destination / name / file
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    (destination / "dependencies.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name in ["LICENSE", "THIRD_PARTY.md"]:
        shutil.copyfile(ROOT / name, destination / name)
    shutil.copytree(ROOT / "licenses", destination / "upstream", dirs_exist_ok=True)


def main():
    os.chdir(ROOT)
    make_icons()
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
               "--name", "MouseShare", "--noupx", "--exclude-module", "tkinter",
               "--exclude-module", "unittest", "--icon", str(ASSETS / (
                   "MouseShare.icns" if sys.platform == "darwin" else "MouseShare.ico")),
               "--collect-submodules", "mouseshare", "--collect-data", "mouseshare"]
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
        content.update({"CFBundleShortVersionString": "0.2.5", "CFBundleVersion": "9",
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
        target = DIST / f"MouseShare-0.2.5-macOS-{platform.machine()}.dmg"
        target.unlink(missing_ok=True)
        run("hdiutil", "create", "-volname", "MouseShare", "-srcfolder", stage,
            "-ov", "-format", "UDZO", target)
    elif sys.platform == "win32":
        licenses(DIST / "MouseShare/licenses")
        run(DIST / "MouseShare/MouseShare.exe", "--smoke-test")
        compiler = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
        run(compiler, ROOT / "packaging/windows.iss")
        shutil.copyfile(ROOT / "docs/INSTALL-Windows.txt", DIST / "MouseShare/安装说明.txt")
        shutil.make_archive(str(DIST / "MouseShare-0.2.5-Windows-x64-portable"), "zip",
                            DIST, "MouseShare")
    else:
        raise RuntimeError("Build on Windows or macOS")


if __name__ == "__main__":
    main()

