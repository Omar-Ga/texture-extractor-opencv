"""Audit the compiled limited-API binary and finalize its stable-ABI wheel tags.

Retagging only rewrites the wheel name and WHEEL metadata; the script fails if any other byte changes.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


def payload(path):
    with zipfile.ZipFile(path) as zf:
        return {n: hashlib.sha256(zf.read(n)).hexdigest() for n in zf.namelist()
                if not n.endswith(("/", ".dist-info/WHEEL", ".dist-info/RECORD"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    report_path = directory / "build-provenance.json"
    info = json.loads(report_path.read_text())
    original = directory / info["wheel"]
    original_sha = hashlib.sha256(original.read_bytes()).hexdigest()
    if original_sha != info["sha256"]:
        raise ValueError("Raw native wheel hash mismatch")
    before = payload(original)
    if "-DPYTHON3_LIMITED_API=ON" not in info["cmake_flags"]:
        raise ValueError("Native binary was not built against the limited API")
    result = subprocess.run([sys.executable, "-m", "wheel", "tags", "--python-tag=cp311", "--abi-tag=abi3", original.name],
                            cwd=directory, capture_output=True, text=True, check=True)
    final = directory / result.stdout.strip().splitlines()[-1]
    if before != payload(final):
        raise ValueError("Retagging changed the native binary or other payload")
    audit = directory / "abi3-audit.json"
    subprocess.run([sys.executable, "-m", "abi3audit", "--strict", "--report", "--output", str(audit), str(final)], check=True)
    audit_data = json.loads(audit.read_text())
    results = [item["result"] for spec in audit_data["specs"].values() for item in spec.get("wheel", [])]
    if not results or not all(r["is_abi3"] and r["is_abi3_baseline_compatible"] for r in results):
        raise ValueError("Stable ABI audit did not verify every Python extension")
    info.update(original_native_wheel=info.get("original_native_wheel", original.name),
                original_native_wheel_sha256=info.get("original_native_wheel_sha256", original_sha),
                wheel=final.name, sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                compatibility_tags="cp311-abi3 (Python 3.11 and later)",
                stable_abi_audit=dict(tool="abi3audit 0.0.26", result="PASS", baseline="3.11", extension_results=results),
                retagging_payload_unchanged=True)
    report_path.write_bytes((json.dumps(info, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps(dict(wheel=final.name, sha256=info["sha256"], stable_abi="PASS", payload_unchanged=True)))


if __name__ == "__main__":
    main()
