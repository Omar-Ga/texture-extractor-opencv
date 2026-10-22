"""Compare a rebuilt wheel with a published one, file by file.

Every file inside the two wheels must be byte-identical. The ZIP containers themselves may still
differ in entry dates or order, so their hashes are reported but not required to match.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def contents(path):
    with zipfile.ZipFile(path) as zf:
        return {name: hashlib.sha256(zf.read(name)).hexdigest() for name in zf.namelist() if not name.endswith("/")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rebuilt", type=Path)
    parser.add_argument("published", type=Path)
    args = parser.parse_args()
    rebuilt, published = contents(args.rebuilt), contents(args.published)
    differing = sorted(n for n in rebuilt.keys() | published.keys() if rebuilt.get(n) != published.get(n))
    whole = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.rebuilt, args.published)]
    print(json.dumps(dict(rebuilt=args.rebuilt.name, published=args.published.name, files=len(published),
                          differing_files=differing, rebuilt_sha256=whole[0], published_sha256=whole[1],
                          wheel_sha256_identical=whole[0] == whole[1],
                          result="REPRODUCED" if not differing else "DIFFERENT"), indent=2))
    sys.exit(1 if differing else 0)


if __name__ == "__main__":
    main()
