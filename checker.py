# run this once to see what's actually in _internal/
from pathlib import Path
internal = Path("dist/FX_Machine/_internal")
for f in sorted(internal.iterdir()):
    print(f.name, f.stat().st_size if f.is_file() else "[dir]")