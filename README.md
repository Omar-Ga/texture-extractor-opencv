# texture-extractor-opencv

The build recipe for the OpenCV library bundled with the [Texture Extractor](https://superhivemarket.com/products/texture-extractor) Blender add-on.

The add-on ships one small compiled file per platform: `wheels/texture_extractor_opencv-4.11.0.86+te3-cp311-abi3-<platform>.whl`. This repository contains everything used to make it. Each wheel is built by the public GitHub Actions workflow in this repository, and GitHub signs a build provenance attestation that ties the wheel's SHA-256 to the exact commit and workflow run that produced it.

## What goes in

| Input | Value |
|---|---|
| Source | Official [opencv-python-headless 4.11.0.86](https://pypi.org/project/opencv-python-headless/4.11.0.86/) source archive from PyPI |
| Source SHA-256 | `996eb282ca4b43ec6a3972414de0e2331f5d9cda2b41091a49739c19fb843798` |
| Changes | Three patch files in [`patches/`](patches/), described below |
| Modules built | `core`, `imgproc`, `dnn` and the Python bindings |
| Switched off | Video I/O, FFmpeg, GStreamer, camera access, GUI, image file codecs, OpenCL, IPP, ITT, LAPACK, Eigen, Java, G-API, non-free code |
| Build settings | The `CMAKE_FLAGS` list in [`build.py`](build.py) |
| Build tools | Pinned in [`requirements/build.txt`](requirements/build.txt) |

### The patches

- [`0001-private-module-name.patch`](patches/0001-private-module-name.patch) is the only change to OpenCV's C++ code. It renames the Python module from `cv2` to `tecv2` (two lines), so the add-on never replaces or clashes with a `cv2` that another Blender add-on installs.
- [`0002-minimal-wheel-packaging.patch`](patches/0002-minimal-wheel-packaging.patch) changes only Python packaging: it stops `setup.py` from looking for files that this minimal build does not produce, marks the wheel as built for Python 3.11 and later, and sets the version to `4.11.0.86+te3`.
- [`0003-repeatable-build-info.patch`](patches/0003-repeatable-build-info.patch) changes one line of the build-information text that `getBuildInformation()` reports: it leaves out the build machine's kernel version, which varies between GitHub's host machines and would otherwise make rebuilds differ.

`build.py` refuses to build if the source archive or any patched file does not match the SHA-256 recorded in it.

## How a wheel is built

[`.github/workflows/build.yml`](.github/workflows/build.yml) runs on GitHub-hosted runners: `manylinux_2_28` (Linux x64), Windows Server 2022 (Windows x64), macOS 15 Intel and macOS 14 Apple Silicon. For each platform it:

1. downloads the source archive and checks its SHA-256,
2. applies the three patches and checks the result,
3. compiles with the flags above,
4. renames the package folder inside the wheel from `cv2` to `tecv2` (compiled files are copied unchanged),
5. checks that no FFmpeg, video codec or TLS libraries ended up in the wheel,
6. audits the binary with `abi3audit` for the stable Python ABI used by Blender 4.5 and later,
7. installs it next to the official `opencv-python-headless` wheel and runs [`smoke_test.py`](smoke_test.py),
8. when asked to reproduce a tag, compares the result with that release (see below).

A tagged run publishes the four wheels, their build reports, test logs and `SHA256SUMS.txt` as a [release](../../releases), and signs an attestation for each wheel.

## Verifying a wheel

The wheel inside the add-on ZIP is the same file as the release asset with the same name.

**With the GitHub CLI:**

```bash
gh attestation verify texture_extractor_opencv-4.11.0.86+te3-cp311-abi3-win_amd64.whl --repo Omar-Ga/texture-extractor-opencv
```

This checks the signature and prints the workflow, commit and run that built the file.

**By hash:** compute the wheel's SHA-256 and compare it with `SHA256SUMS.txt` in the release and with the [attestations page](../../attestations).

- Windows: `certutil -hashfile <wheel> SHA256`
- macOS: `shasum -a 256 <wheel>`
- Linux: `sha256sum <wheel>`

## Reproducing a release

Builds are repeatable: the build date is fixed through `SOURCE_DATE_EPOCH`, the build machine's kernel version is left out of the build information, and Windows builds use `/Brepro` so the compiler and linker write content hashes instead of timestamps. Rebuilding a tag on the same runner images gives byte-identical files inside every wheel.

To check a release yourself, fork this repository, open **Actions > Build > Run workflow**, and enter the tag (for example `v4.11.0.86+te3`) as **reproduce_tag**. Each platform job rebuilds that tag from source, downloads the published wheel, and runs [`compare.py`](compare.py), which fails unless every file inside the two wheels is byte-identical. The result is in each job's log and in `reproduction.txt` in its artifact.

To build locally instead, with Python 3.11, git, CMake and a C++ compiler:

```bash
python -m pip install -r requirements/build.txt
python build.py --work-dir build --output-dir dist
python finalize.py dist
```

A local build uses a different compiler and system libraries than the GitHub runners, so expect the same behaviour but not the same bytes.

## License

The scripts and patches in this repository are licensed under Apache-2.0, the same license as OpenCV. Built wheels contain OpenCV's license and all third-party notices.
