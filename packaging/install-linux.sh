#!/bin/sh
# Install versioned copies as the current user; existing app data is kept separately.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
user_root=${MOUSESHARE_INSTALL_ROOT:-"$HOME/.local"}
version=0.7.4
version_dir="$user_root/opt/MouseShare-$version"
link="$user_root/opt/MouseShare"
marker=io.github.makesail.mouseshare
if [ -e "$link" ] || [ -L "$link" ]; then
    if [ ! -L "$link" ] || [ ! -f "$link/.mouseshare-install" ] || [ "$(cat "$link/.mouseshare-install")" != "$marker" ]; then
        printf '%s\n' 'Existing MouseShare path is not managed by this installer; choose a different MOUSESHARE_INSTALL_ROOT.' >&2
        exit 1
    fi
fi
if [ -e "$version_dir" ]; then
    printf '%s\n' "Version already exists: $version_dir. Use its MouseShare executable or choose another install root." >&2
    exit 1
fi
mkdir -p "$user_root/opt" "$user_root/share/applications"
mkdir "$version_dir"
cp -R "$source_dir/." "$version_dir/"
printf '%s\n' "$marker" > "$version_dir/.mouseshare-install"
chmod +x "$version_dir/MouseShare"
link_temp="$link.new.$$"
ln -s "$version_dir" "$link_temp"
mv -Tf "$link_temp" "$link"
escaped=$(printf '%s' "$link/MouseShare" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/`/\\`/g' -e 's/\$/\\$/g' -e 's/%/%%/g')
cat > "$user_root/share/applications/io.github.makesail.mouseshare.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MouseShare
Comment=Share keyboard, mouse, clipboard and files
Exec="$escaped"
Icon=$link/mouseshare.png
Terminal=false
Categories=Utility;Network;
StartupWMClass=MouseShare
EOF
printf '%s\n' "Installed: $link/MouseShare" 'Start MouseShare from your application menu. Choose an X11/Xorg session for keyboard and mouse sharing.'
