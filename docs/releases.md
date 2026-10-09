# CI and release management

GitHub Actions checks Python and shell syntax, JSON metadata, the desktop
launcher, and the built Debian package on pushes to `main`, pull requests,
and manual runs. Download the `.deb` and `SHA256SUMS` from the run's
`debian-package` artifact (kept for 30 days).

An additional Ubuntu 24.04 job compiles the module against HWE kernel
`7.0.0-38-generic`, using exact `linux-hwe-7.0` sources fetched automatically
through isolated, authenticated APT metadata. Release publication requires
both the package checks and this HWE build to pass. The pinned headers and
sources must remain available in Ubuntu's repositories; update the pin and
revalidate together when moving to a newer kernel.
CI does not install the driver package or load a module, and does not test
hardware. See [packaging](packaging.md) for the broader kernel build matrix.

## Publish a release

1. Update `VERSION` and the installation example in `docs/packaging.md`.
   For example, set `VERSION` to `0.1.0~beta5`.
2. Commit and push the changes to `main`. Check that its Actions run succeeds.
3. Tag that commit and push the tag:

   ```sh
   git tag -a v0.1.0-beta5 -m "Eleven Rack Control 0.1.0 beta5"
   git push origin v0.1.0-beta5
   ```

The tag pipeline repeats all checks before publishing a GitHub Release with
the `.deb`, SHA-256 checksums, and generated release notes. Tags must match
`VERSION`: `v0.1.0-beta5` becomes Debian version `0.1.0~beta5`.
An underscore is also accepted: `v0.1.0_beta4` maps to `0.1.0~beta4`.
`alpha`, `beta`, and `rc` tags create prereleases; `v0.1.0` creates a stable
release. Only use a stable tag once the release is ready for that status.

No extra secret is needed: the release job uses GitHub's built-in token with
`contents: write`. Build and pull request jobs have read-only permissions.
GitHub Actions must be enabled for the repository.

Published releases are preserved on reruns. To change package contents, bump
the version and publish a new tag rather than replacing an existing release.

Users can verify downloaded files with `sha256sum --check SHA256SUMS` and
install the downloaded `.deb` using `sudo apt install ./eleven-rack-driver_*.deb`.

The release command uses GitHub CLI's
[release creation options](https://cli.github.com/manual/gh_release_create).
