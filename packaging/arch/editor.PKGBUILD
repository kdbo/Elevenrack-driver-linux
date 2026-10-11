pkgname=eleven-rack-editor-linux
pkgver=@VERSION@
pkgrel=1
pkgdesc='Eleven Rack Editor with the Linux MIDI bridge'
arch=('x86_64')
url='https://github.com/kdbo/Elevenrack-driver-linux'
license=('MIT')
options=('!strip' '!debug')
depends=('python' 'python-rtmidi' 'python-websockets' 'alsa-lib' 'gtk3' 'nss'
         'nspr' 'libxss' 'libxtst' 'libdrm' 'mesa' 'libxcomposite' 'libxdamage'
         'libxrandr' 'libxkbcommon' 'libcups' 'at-spi2-core' 'pango' 'cairo'
         'dbus' 'expat' 'glibc' 'libgcc' 'libstdc++')
optdepends=('eleven-rack-driver: DKMS driver, Control and calibrated latency backend')
source=('eleven-rack-editor.tar.gz')
sha256sums=('@EDITOR_SHA256@')
package() {
    install -dm755 "$pkgdir/opt"
    cp -a "$srcdir/eleven-rack-editor" "$pkgdir/opt/eleven-rack-editor"
    chmod 4755 "$pkgdir/opt/eleven-rack-editor/chrome-sandbox"
    install -Dm755 "$pkgdir/opt/eleven-rack-editor/arch-launcher" "$pkgdir/usr/bin/eleven-rack-editor-linux"
    install -Dm644 "$pkgdir/opt/eleven-rack-editor/arch.desktop" "$pkgdir/usr/share/applications/eleven-rack-editor-linux.desktop"
    install -Dm644 "$pkgdir/opt/eleven-rack-editor/resources/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 "$pkgdir/opt/eleven-rack-editor/resources/NOTICE" "$pkgdir/usr/share/doc/$pkgname/NOTICE"
}
