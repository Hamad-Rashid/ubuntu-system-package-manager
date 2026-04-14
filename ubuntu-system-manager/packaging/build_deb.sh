#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_NAME="ubuntu-system-manager"
VERSION="${1:-0.4.0}"
ARCH="${2:-$(dpkg --print-architecture)}"
OUTPUT_DIR="${ROOT_DIR}/dist"
STAGE_DIR="$(mktemp -d)"
PKG_DIR="${STAGE_DIR}/${PKG_NAME}_${VERSION}_${ARCH}"
APP_DIR="/usr/lib/${PKG_NAME}"

cleanup() {
  rm -rf "${STAGE_DIR}"
}
trap cleanup EXIT

mkdir -p \
  "${PKG_DIR}/DEBIAN" \
  "${PKG_DIR}${APP_DIR}" \
  "${PKG_DIR}/usr/bin" \
  "${PKG_DIR}/usr/share/applications"

cp -a \
  "${ROOT_DIR}/src" \
  "${ROOT_DIR}/run.sh" \
  "${ROOT_DIR}/requirements.txt" \
  "${ROOT_DIR}/README.md" \
  "${PKG_DIR}${APP_DIR}/"

cat > "${PKG_DIR}/usr/bin/ubuntu-system-manager" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/usr/lib/ubuntu-system-manager"
export PYTHONPATH="${APP_DIR}/src:${PYTHONPATH:-}"
exec python3 -m ubuntu_system_manager.main "$@"
LAUNCHER
chmod 0755 "${PKG_DIR}/usr/bin/ubuntu-system-manager"

cat > "${PKG_DIR}/usr/share/applications/ubuntu-system-manager.desktop" <<'DESKTOP'
[Desktop Entry]
Version=1.0
Type=Application
Name=Ubuntu System Manager
Comment=System packages, mounts, bluetooth and health actions
Exec=ubuntu-system-manager
Icon=utilities-system-monitor
Terminal=false
Categories=System;Utility;
StartupNotify=true
DESKTOP
chmod 0644 "${PKG_DIR}/usr/share/applications/ubuntu-system-manager.desktop"

cat > "${PKG_DIR}/DEBIAN/control" <<CONTROL
Package: ${PKG_NAME}
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: ${ARCH}
Maintainer: Hamad <hamad@example.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, util-linux, ntfs-3g, bluez, snapd, policykit-1
Description: Ubuntu desktop system manager with package and partition actions
 A GTK4 + Libadwaita desktop app for Ubuntu system metrics,
 package operations (APT/Snap), bluetooth status, and
 partition mount/fix workflows via pkexec.
CONTROL
chmod 0644 "${PKG_DIR}/DEBIAN/control"

mkdir -p "${OUTPUT_DIR}"
DEB_PATH="${OUTPUT_DIR}/${PKG_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --build "${PKG_DIR}" "${DEB_PATH}"

echo "Built package: ${DEB_PATH}"
