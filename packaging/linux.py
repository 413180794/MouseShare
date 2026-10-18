"""Build relocatable Linux tarballs and native Debian packages, without root."""
import platform
import shutil
import subprocess

DEPENDENCIES = ('libc6 (>= 2.35), libstdc++6, libgcc-s1, libx11-6, libxi6, libxtst6, libxfixes3, libxrandr2, '
                'libxss1, libxkbcommon0, libxkbcommon-x11-0, libxcb1, libxcb-cursor0, libxcb-icccm4, '
                'libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render0, libxcb-render-util0, '
                'libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0, libxcb-xinerama0, '
                'libxcb-xkb1, libgl1, libegl1, libopengl0, libdbus-1-3, libfontconfig1, libfreetype6, libglib2.0-0')


def build_linux(root, dist, version):
    from mouseshare.startup import desktop_entry
    architecture = {'x86_64': ('x64', 'amd64'), 'aarch64': ('arm64', 'arm64')}[platform.machine()]
    label, deb_arch = architecture
    app = dist / 'MouseShare'
    shutil.copyfile(root / 'build/icons/icon-256.png', app / 'mouseshare.png')
    shutil.copyfile(root / 'docs/INSTALL-Linux.txt', app / 'README-Linux.txt')
    shutil.copyfile(root / 'packaging/install-linux.sh', app / 'install.sh')
    (app / 'install.sh').chmod(0o755)
    stage = root / 'build/linux-deb'
    shutil.rmtree(stage, ignore_errors=True)
    target = stage / 'opt/mouseshare'
    shutil.copytree(app, target, symlinks=True)
    control = stage / 'DEBIAN'
    control.mkdir()
    size = sum(p.stat().st_size for p in target.rglob('*') if p.is_file()) // 1024
    (control / 'control').write_text(
        f'Package: mouseshare\nVersion: {version}\nArchitecture: {deb_arch}\n'
        'Maintainer: MouseShare contributors <mouseshare@users.noreply.github.com>\n'
        f'Installed-Size: {size}\nDepends: {DEPENDENCIES.replace("2.35", "2.39") if deb_arch == "arm64" else DEPENDENCIES}\n'
        'Section: utils\nPriority: optional\nHomepage: https://github.com/413180794/MouseShare\n'
        'Description: Encrypted LAN keyboard, mouse, clipboard and file sharing\n'
        ' Keyboard and mouse sharing requires a logged-in X11 desktop.\n'
        ' Wayland offers file transfers and foreground manual clipboard sharing.\n', encoding='utf-8')
    desktop = stage / 'usr/share/applications'
    desktop.mkdir(parents=True)
    entry = desktop_entry(['/opt/mouseshare/MouseShare'])
    entry += 'Icon=mouseshare\nStartupWMClass=MouseShare\n'
    (desktop / 'io.github.makesail.mouseshare.desktop').write_text(entry, encoding='utf-8')
    icons = stage / 'usr/share/icons/hicolor/256x256/apps'
    icons.mkdir(parents=True)
    shutil.copyfile(app / 'mouseshare.png', icons / 'mouseshare.png')
    package = dist / f'MouseShare-{version}-Linux-{label}.deb'
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(package)], check=True)
    shutil.make_archive(str(dist / f'MouseShare-{version}-Linux-{label}'), 'gztar', dist, 'MouseShare')
    return package
