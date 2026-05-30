"""Final PYZ diagnostic — reads the tail-located TOC. Delete after use."""
from pathlib import Path
import struct
import zlib
import marshal

data = Path('dist/FX_Machine/FX_Machine.exe').read_bytes()

pyz_offset = 369039
pyz_size = 2598963
pyz_data = data[pyz_offset:pyz_offset + pyz_size]

print(f"PYZ size: {len(pyz_data)} bytes")

# Read the header
magic = pyz_data[:4]
py_magic = pyz_data[4:8]
toc_offset_in_pyz = struct.unpack_from(">I", pyz_data, 8)[0]
reserved = struct.unpack_from(">I", pyz_data, 12)[0]

print(f"PYZ magic: {magic}")
print(f"Python magic: {py_magic.hex()}")
print(f"TOC offset within PYZ: {toc_offset_in_pyz}")
print(f"Reserved field: {reserved}")

# The TOC is at the end of the PYZ
toc_start = toc_offset_in_pyz
toc_size = len(pyz_data) - toc_start
toc_blob = pyz_data[toc_start:]

print(f"\nTOC region: offset {toc_start} to {len(pyz_data)}, size {toc_size} bytes")
print(f"TOC first 32 hex: {toc_blob[:32].hex()}")
print(f"TOC first 32 repr: {toc_blob[:32]!r}")

# The TOC might be raw marshal data, or zlib-compressed marshal data
# Check if it starts with zlib magic
if toc_blob[:2] in (b'\x78\x9c', b'\x78\x01', b'\x78\xda'):
    print(f"\nTOC appears zlib-compressed (starts with {toc_blob[:2].hex()})")
    try:
        toc_decompressed = zlib.decompress(toc_blob)
        print(f"TOC decompressed: {len(toc_decompressed)} bytes")
        toc_obj = marshal.loads(toc_decompressed)
        print(f"TOC type: {type(toc_obj).__name__}")
    except Exception as e:
        print(f"TOC decompress+marshal failed: {e}")
        toc_obj = None
else:
    print(f"\nTOC does not start with zlib magic, trying raw marshal...")
    try:
        toc_obj = marshal.loads(toc_blob)
        print(f"TOC type: {type(toc_obj).__name__}")
    except Exception as e:
        print(f"Raw marshal failed: {e}")
        # Try skipping some header bytes
        for skip in range(1, 16):
            try:
                toc_obj = marshal.loads(toc_blob[skip:])
                print(f"Marshal succeeded after skipping {skip} bytes, type: {type(toc_obj).__name__}")
                break
            except:
                pass
        else:
            print("Could not unmarshal TOC with any offset")
            toc_obj = None

# Examine the TOC
if toc_obj is not None:
    if isinstance(toc_obj, dict):
        print(f"\nTOC is a dict with {len(toc_obj)} entries")

        # Show key types
        key_types = set(type(k).__name__ for k in toc_obj)
        print(f"Key types: {key_types}")

        # Show value types (first few)
        val_types = set()
        for i, (k, v) in enumerate(toc_obj.items()):
            val_types.add(type(v).__name__)
            if i >= 5:
                break
        print(f"Value types (sample): {val_types}")

        # Show first 5 entries
        print(f"\nFirst 5 entries:")
        for i, (k, v) in enumerate(toc_obj.items()):
            if i >= 5:
                break
            v_repr = repr(v)
            if len(v_repr) > 100:
                v_repr = v_repr[:100] + "..."
            print(f"  key={k!r}  value={v_repr}")

        # Count src.* modules
        src_keys = sorted(k for k in toc_obj if isinstance(k, str) and k.startswith("src."))
        print(f"\nsrc.* modules: {len(src_keys)}")
        for k in src_keys:
            print(f"  {k}")

        # Count other interesting packages
        for prefix in ["pygame", "pythonosc", "tkinter", "psutil", "_"]:
            pkg_keys = [k for k in toc_obj if isinstance(k, str) and k.startswith(prefix)]
            if pkg_keys:
                print(f"\n{prefix}* modules: {len(pkg_keys)}")

    elif isinstance(toc_obj, (list, tuple)):
        print(f"\nTOC is a {type(toc_obj).__name__} with {len(toc_obj)} entries")
        if len(toc_obj) > 0:
            print(f"First entry: {toc_obj[0]!r}")
            # Try to extract names
            names = set()
            for entry in toc_obj:
                if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                    if isinstance(entry[0], str):
                        names.add(entry[0])
            src_names = sorted(n for n in names if n.startswith("src."))
            print(f"src.* modules: {len(src_names)}")
            for n in src_names:
                print(f"  {n}")
    else:
        print(f"\nUnexpected TOC type: {type(toc_obj).__name__}")
        print(f"repr[:500]: {repr(toc_obj)[:500]}")

print("\nDone.")