#!/bin/sh
# 构建 Linux ARM64 安装包：.deb 与通用 tar.gz
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"

VERSION=$(python3 -c "from pcl_core.config import APP_VERSION; print(APP_VERSION)")
ARCH=arm64
DIST="$ROOT/dist"
STAGE=$(mktemp -d)
TARSTAGE=$(mktemp -d)
trap 'rm -rf "$STAGE" "$TARSTAGE"' EXIT

python3 tools/build_single.py
mkdir -p "$DIST"

# ---- .deb ----
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/pcl-launcher" \
    "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/256x256/apps" \
    "$STAGE/usr/share/doc/pcl-launcher"

install -m 755 pcl-single.py "$STAGE/usr/share/pcl-launcher/pcl-single.py"
install -m 755 packaging/linux/pcl-launcher "$STAGE/usr/bin/pcl-launcher"
install -m 644 packaging/linux/pcl-launcher.desktop "$STAGE/usr/share/applications/pcl-launcher.desktop"
install -m 644 packaging/linux/pcl-launcher.png "$STAGE/usr/share/icons/hicolor/256x256/apps/pcl-launcher.png"
install -m 644 README.md "$STAGE/usr/share/doc/pcl-launcher/README.md"
[ -f LICENSE ] && install -m 644 LICENSE "$STAGE/usr/share/doc/pcl-launcher/LICENSE"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: pcl-launcher
Version: $VERSION
Section: games
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, gir1.2-webkit2-4.0 | gir1.2-webkit2-4.1
Installed-Size: $(du -sk "$STAGE/usr" | cut -f1)
Maintainer: thy2014 <thy2014@users.noreply.github.com>
Description: PCL Launcher - Minecraft launcher for Linux ARM64
 A PCL-style Minecraft launcher with a native desktop window,
 version, loader, Modrinth, account, server and diagnostic features.
 The window uses the system GTK3 + WebKit2GTK runtime; the same web
 UI is shipped in the Windows single-file build.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

DEB="$DIST/PCL-Launcher_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$DEB"

# ---- 通用 tar.gz（不依赖 dpkg 的发行版）----
PKGNAME="PCL-Launcher_${VERSION}_linux_${ARCH}"
mkdir -p "$TARSTAGE/$PKGNAME"
cp pcl-single.py packaging/linux/install.sh packaging/linux/uninstall.sh \
    packaging/linux/pcl-launcher.png README.md LICENSE "$TARSTAGE/$PKGNAME/"
chmod 755 "$TARSTAGE/$PKGNAME/install.sh" "$TARSTAGE/$PKGNAME/uninstall.sh" "$TARSTAGE/$PKGNAME/pcl-single.py"
tar -czf "$DIST/$PKGNAME.tar.gz" -C "$TARSTAGE" "$PKGNAME"

echo "built:"
ls -lh "$DEB" "$DIST/$PKGNAME.tar.gz"
