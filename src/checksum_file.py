import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])

h = hashlib.sha256()

with path.open("rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        h.update(chunk)

print(h.hexdigest())
