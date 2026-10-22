"""Build the minimal, CPU-only OpenCV wheel used by Texture Extractor.

Downloads the official opencv-python-headless 4.11.0.86 source archive, checks its
SHA-256, applies the patches in patches/, and builds with the CMake flags below.
Linux builds must run in the manylinux_2_28 container.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE_URL = "https://files.pythonhosted.org/packages/36/2f/5b2b3ba52c864848885ba988f24b7f105052f68da9ab0e693cc7c25b0b30/opencv-python-headless-4.11.0.86.tar.gz"
SOURCE_SHA256 = "996eb282ca4b43ec6a3972414de0e2331f5d9cda2b41091a49739c19fb843798"
VERSION = "4.11.0.86+te3"
PATCHES = ("0001-private-module-name.patch", "0002-minimal-wheel-packaging.patch")
PATCHED_SHA256 = {
    "opencv/modules/python/src2/cv2.cpp": "70c3739d5f41aa6d96006661c14af716db95f2bed0f4b6cefd5f1a3e355f8f77",
    "opencv/modules/python/src2/cv2.hpp": "753e77e0781a7c9238510fc264a9f0359082034dbce4120a7d6518360f507465",
    "setup.py": "28e0d45a970428fa07b5152cd99e6717c9da77fa8659df839ce5667b11f05cce",
}
PRIVATE_DISTRIBUTION = "texture_extractor_opencv"
PRIVATE_MODULE = "tecv2"
CMAKE_FLAGS = [
    "-DBUILD_LIST=core,imgproc,dnn,python3",
    "-DPYTHON3_LIMITED_API=ON",
    "-DWITH_FFMPEG=OFF", "-DWITH_GSTREAMER=OFF", "-DWITH_MSMF=OFF",
    "-DWITH_AVFOUNDATION=OFF", "-DWITH_V4L=OFF", "-DWITH_OPENCL=OFF",
    "-DWITH_IPP=OFF", "-DWITH_ITT=OFF", "-DWITH_LAPACK=OFF",
    "-DWITH_EIGEN=OFF", "-DWITH_OPENEXR=OFF", "-DWITH_OPENJPEG=OFF",
    "-DWITH_TIFF=OFF", "-DWITH_WEBP=OFF", "-DWITH_JPEG=OFF", "-DWITH_PNG=OFF",
    "-DWITH_PROTOBUF=ON", "-DBUILD_PROTOBUF=ON", "-DPROTOBUF_UPDATE_FILES=OFF",
    "-DBUILD_opencv_apps=OFF", "-DBUILD_TESTS=OFF", "-DBUILD_PERF_TESTS=OFF",
    "-DBUILD_EXAMPLES=OFF", "-DBUILD_DOCS=OFF", "-DBUILD_JAVA=OFF",
    "-DBUILD_opencv_java=OFF", "-DBUILD_opencv_gapi=OFF",
    "-DBUILD_opencv_videoio=OFF", "-DBUILD_opencv_highgui=OFF",
    "-DOPENCV_ENABLE_NONFREE=OFF", "-DENABLE_PRECOMPILED_HEADERS=OFF",
]
FORBIDDEN_PAYLOAD = ("avcodec", "avformat", "ffmpeg", "x264", "x265", "gnutls", "libssl", "libcrypto")


def run(args, **kwargs):
    print("RUN", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def text_sha256(path):
    """Hash with LF line endings, so the check is the same on every platform."""
    return sha256(path.read_bytes().replace(b"\r\n", b"\n"))


def apply_patches(source):
    for name in PATCHES:
        run(["git", "-c", "core.autocrlf=false", "apply", "--whitespace=nowarn", "--verbose", ROOT / "patches" / name],
            cwd=source)
    for relative, expected in PATCHED_SHA256.items():
        actual = text_sha256(source / relative)
        if actual != expected:
            raise RuntimeError(f"Patched {relative} has SHA-256 {actual}, expected {expected}")
    if f'opencv_version = "{VERSION}"' not in (source / "cv2/version.py").read_text():
        raise RuntimeError("Patched version does not match build.py VERSION")


def extend_notices(source):
    notices = source / "LICENSE-3RD-PARTY.txt"
    scope = (
        "Texture Extractor minimal OpenCV build\n"
        "This is a modified build of opencv-python-headless 4.11.0.86.\n"
        "Only core, imgproc, dnn and Python bindings are built. FFmpeg, video I/O,\n"
        "GUI, image codecs, IPP, ITT, LAPACK and OpenCL are disabled.\n"
        "The Python binding entry point and namespace are renamed to tecv2, and\n"
        "the wheel distribution is texture-extractor-opencv, to avoid cv2 conflicts.\n"
        "Build recipe: https://github.com/Omar-Ga/texture-extractor-opencv\n"
        "Upstream packaging notices below are retained for provenance; their\n"
        "references to multimedia libraries do not describe this custom build.\n\n"
    )
    extra = []
    for base in [source / "opencv/3rdparty", source / "opencv/modules/core", source / "opencv/modules/dnn"]:
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.name.lower().startswith(("license", "copying", "copyright", "notice")):
                if path.stat().st_size < 200_000:
                    extra.append(f"\n--- {path.relative_to(source)} ---\n" + path.read_text(errors="replace"))
    notices.write_text(scope + notices.read_text() + "\n".join(extra))


def privatize_wheel(original):
    """Rename the cv2 package to tecv2 inside the wheel. Compiled files are copied unchanged."""
    from wheel.wheelfile import WheelFile
    target = original.with_name(PRIVATE_DISTRIBUTION + "-" + original.name.split("-", 1)[1])
    with zipfile.ZipFile(original) as source, WheelFile(str(target), "w") as dest:
        for name in source.namelist():
            if name.endswith(("/", ".dist-info/RECORD")):
                continue
            data = source.read(name)
            private_name = name.replace("opencv_python_headless-", PRIVATE_DISTRIBUTION + "-", 1)
            if private_name.startswith("cv2/"):
                private_name = PRIVATE_MODULE + private_name[3:]
                leaf = private_name.rsplit("/", 1)[-1]
                if leaf.startswith("cv2.") and leaf.endswith((".pyd", ".so")):
                    private_name = private_name.rsplit("/", 1)[0] + "/" + PRIVATE_MODULE + leaf[3:]
                if private_name.endswith(".py"):
                    data = re.sub(rb"\bcv2\b", PRIVATE_MODULE.encode(), data)
                    data = data.replace(b"OpenCV_LOADER", b"TEXTURE_EXTRACTOR_OPENCV_LOADER")
            if private_name.endswith(".dist-info/METADATA"):
                data = data.replace(b"Name: opencv-python-headless", b"Name: texture-extractor-opencv")
                data = re.sub(rb"(?m)^Summary:.*$", b"Summary: Private minimal OpenCV binding for Texture Extractor", data)
            dest.writestr(private_name, data)
    return target


def ci_context():
    keys = ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "ImageOS", "ImageVersion")
    context = {k.lower(): os.environ[k] for k in keys if k in os.environ}
    if "GITHUB_RUN_ID" in os.environ:
        context["run_url"] = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    work, output = args.work_dir.resolve(), args.output_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    archive = work / "opencv-python-headless-4.11.0.86.tar.gz"
    if not archive.exists():
        urllib.request.urlretrieve(SOURCE_URL, archive)
    if sha256(archive.read_bytes()) != SOURCE_SHA256:
        raise RuntimeError("Upstream source archive hash mismatch")
    source = work / "opencv-python-headless-4.11.0.86"
    if source.exists():
        raise RuntimeError("Use a fresh work directory to avoid stale build outputs")
    with tarfile.open(archive) as tf:
        tf.extractall(work, filter="data")
    apply_patches(source)
    extend_notices(source)
    env = os.environ.copy()
    env.update(ENABLE_HEADLESS="1", ENABLE_CONTRIB="0", CMAKE_BUILD_PARALLEL_LEVEL="2",
               CMAKE_ARGS=" ".join(CMAKE_FLAGS))
    if sys.platform == "darwin":
        env["MACOSX_DEPLOYMENT_TARGET"] = "13.0"
    raw = work / "raw-wheels"
    run([sys.executable, "-m", "pip", "wheel", "--no-build-isolation", "--no-deps", "--verbose",
         "--wheel-dir", raw, source], env=env)
    upstream_wheel, = raw.glob("*.whl")
    wheel = privatize_wheel(upstream_wheel)
    if sys.platform.startswith("linux"):
        run([sys.executable, "-m", "auditwheel", "repair", "--plat",
             "manylinux_2_28_" + platform.machine(), "--wheel-dir", output, wheel])
    elif sys.platform == "darwin":
        run([sys.executable, "-m", "delocate.cmd.delocate_wheel", "--wheel-dir", output, wheel])
    else:
        shutil.copy2(wheel, output / wheel.name)
    final, = output.glob("*.whl")
    with zipfile.ZipFile(final) as zf:
        forbidden = [n for n in zf.namelist() if any(s in n.lower() for s in FORBIDDEN_PAYLOAD)]
        if forbidden:
            raise RuntimeError(f"Unexpected multimedia/crypto binaries: {forbidden}")
    report = dict(version=VERSION, source_url=SOURCE_URL, source_sha256=SOURCE_SHA256,
                  distribution="texture-extractor-opencv", import_name=PRIVATE_MODULE,
                  patches={name: sha256((ROOT / "patches" / name).read_bytes().replace(b"\r\n", b"\n")) for name in PATCHES},
                  patched_source_sha256=PATCHED_SHA256,
                  cmake_flags=CMAKE_FLAGS, platform=platform.platform(), machine=platform.machine(),
                  python=sys.version, ci=ci_context(), wheel=final.name, sha256=sha256(final.read_bytes()))
    (output / "build-provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
