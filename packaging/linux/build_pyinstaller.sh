#!/bin/sh
# 构建 Linux ARM64 自带 Python 运行时的单文件窗口程序，并打包为 .deb 与 tar.gz
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"

VERSION=$(python3 -c "from pcl_core.config import APP_VERSION; print(APP_VERSION)")
ARCH=arm64
DIST="$ROOT/dist"
WORK=$(mktemp -d)
STAGE=$(mktemp -d)
TARSTAGE=$(mktemp -d)
trap 'rm -rf "$WORK" "$STAGE" "$TARSTAGE"' EXIT

mkdir -p "$DIST"

# 保持源码分发的单文件版本与当前源码一致；安装包本身不再依赖它。
python3 tools/build_single.py

echo "[1/4] PyInstaller 单文件（内置 Python 3 运行时）"
python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name "PCL-Launcher" \
  --distpath "$WORK/dist" \
  --workpath "$WORK/build" \
  --specpath "$WORK" \
  --add-data "$ROOT/web:web" \
  --collect-all webview \
  --collect-all gi \
  --hidden-import "webview.platforms.gtk" \
  pcl.py

BIN="$WORK/dist/PCL-Launcher"
test -x "$BIN"
install -m 755 "$BIN" "$DIST/PCL-Launcher-linux-arm64"

echo "[2/4] 构建 .deb（不依赖系统 python3）"
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/bin" "$STAGE/usr/share/pcl-launcher" \
    "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/256x256/apps" \
    "$STAGE/usr/share/doc/pcl-launcher"
install -m 755 "$BIN" "$STAGE/usr/bin/pcl-launcher"
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
Depends: gir1.2-gtk-3.0, gir1.2-webkit2-4.0 | gir1.2-webkit2-4.1
Installed-Size: $(du -sk "$STAGE/usr" | cut -f1)
Maintainer: thy2014 <thy2014@users.noreply.github.com>
Description: PCL Launcher - Minecraft launcher for Linux ARM64
 A PCL-style Minecraft launcher with a native desktop window.
 The executable bundles its own Python 3 runtime; the system only
 provides GTK3 + WebKit2GTK for the window shell.
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

echo "[3/4] 构建通用 tar.gz"
PKGNAME="PCL-Launcher_${VERSION}_linux_${ARCH}"
mkdir -p "$TARSTAGE/$PKGNAME"
install -m 755 "$BIN" "$TARSTAGE/$PKGNAME/PCL-Launcher"
cp packaging/linux/install.sh packaging/linux/uninstall.sh \
    packaging/linux/pcl-launcher.png README.md LICENSE "$TARSTAGE/$PKGNAME/"
chmod 755 "$TARSTAGE/$PKGNAME/install.sh" "$TARSTAGE/$PKGNAME/uninstall.sh"
tar -czf "$DIST/$PKGNAME.tar.gz" -C "$TARSTAGE" "$PKGNAME"

echo "[4/4] 完成"
ls -lh "$DIST/PCL-Launcher-linux-arm64" "$DEB" "$DIST/$PKGNAME.tar.gz"
