# CI and release management

GitHub Actions checks Python and shell syntax, JSON metadata, the desktop
launcher, and the built Debian packages on release-tag pushes, pull requests,
and manual runs. Ordinary pushes to `main` do not start this full build,
so pushing a release commit and its tag does not build the packages twice. Download the `.deb` and `SHA256SUMS` from the run's
`debian-package` artifact (kept for 30 days).

An additional Ubuntu 24.04 job compiles the module against HWE kernel
`7.0.0-38-generic`, using exact `linux-hwe-7.0` sources fetched automatically
through isolated, authenticated APT metadata. Release publication requires
the driver package checks, this HWE build, and the editor build to pass.
The pinned headers and sources must remain available in Ubuntu's repositories; update the pin and
revalidate together when moving to a newer kernel.
CI does not install the driver package or load a module, and does not test
hardware. See [packaging](packaging.md) for the broader kernel build matrix.

## Editor package

The same workflow tests the editor and builds an amd64 `.deb` on Ubuntu 24.04
using Node.js 22, `npm ci`, and Electron Builder. On manual and pull request
runs, it is available in the `editor-debian-package` artifact for 30 days.

`VERSION` is the shared release version for both packages. The build converts
`0.1.2~beta1` to Electron's `0.1.2-beta1`; Electron Builder converts it back to
`0.1.2~beta1` in the Debian metadata. The source `editor/package.json` and lockfile
are not rewritten. CI checks the package identity, version, architecture,
application archive, Python bridge, desktop launcher, and icon before uploading.
Hardware operation and installation are not tested by this job.

## Publish a release

1. Update `VERSION` and the installation example in `docs/packaging.md`.
   For example, set `VERSION` to `0.1.2~beta1`.
2. Commit and push the changes to `main`. Validate locally, or run **Build and
   release** manually from Actions before tagging. Pull requests also run it.
3. Tag that commit and push the tag:

   ```sh
   git tag -a v0.1.2-beta1 -m "Eleven Rack Linux 0.1.2 beta1"
   git push origin v0.1.2-beta1
   ```

The tag pipeline repeats all checks before publishing a GitHub Release with
both the driver and editor `.deb` files, a shared `SHA256SUMS` file, and
generated release notes. Tags must match
`VERSION`: `v0.1.2-beta1` becomes Debian version `0.1.2~beta1`.
An underscore is also accepted: `v0.1.0_beta4` maps to `0.1.0~beta4`.
`alpha`, `beta`, and `rc` tags create prereleases; `v0.1.0` creates a stable
release. Only use a stable tag once the release is ready for that status.

No extra secret is needed: the release job uses GitHub's built-in token with
`contents: write`. Build and pull request jobs have read-only permissions.
GitHub Actions must be enabled for the repository.

Published releases are preserved on reruns. To change package contents, bump
the version and publish a new tag rather than replacing an existing release.

Users can verify downloaded files with `sha256sum --check SHA256SUMS` and
install the required package using `sudo apt install ./eleven-rack-driver_*.deb`
or `sudo apt install ./eleven-rack-editor-linux_*.deb`. The editor is separate
from the driver and is not installed automatically with it.

The release command uses GitHub CLI's
[release creation options](https://cli.github.com/manual/gh_release_create).
