"""Temporary diagnostic script — delete after use."""
from pathlib import Path
import struct
import zlib

data = Path('dist/FX_Machine/FX_Machine.exe').read_bytes()
print(f"EXE size: {len(data)} bytes")

# Find CArchive
magic = b'MEI\014\013\012\013\016'
magic_pos = data.rfind(magic)
print(f"Magic at offset {magic_pos}")

footer = data[magic_pos:]

archive_len = struct.unpack_from('>I', footer, 8)[0]
toc_offset  = struct.unpack_from('>I', footer, 12)[0]
toc_size    = struct.unpack_from('>I', footer, 16)[0]
py_ver      = struct.unpack_from('>I', footer, 20)[0]

archive_start = len(data) - archive_len
toc_start = archive_start + toc_offset

print(f"archive_len={archive_len}  archive_start={archive_start}")
print(f"toc_offset={toc_offset}  toc_size={toc_size}  toc_start={toc_start}")
print(f"py_ver={py_ver}")

toc_data = data[toc_start:toc_start + toc_size]

# Parse TOC entries
pos = 0
entries = []
while pos < len(toc_data):
    if pos + 18 > len(toc_data):
        break
    entry_len = struct.unpack_from('>I', toc_data, pos)[0]
    data_offset = struct.unpack_from('>I', toc_data, pos + 4)[0]
    comp_size = struct.unpack_from('>I', toc_data, pos + 8)[0]
    uncomp_size = struct.unpack_from('>I', toc_data, pos + 12)[0]
    is_comp = toc_data[pos + 16]
    type_code = chr(toc_data[pos + 17])
    name_start = pos + 18
    name_end = toc_data.find(b'\x00', name_start)
    if name_end == -1 or name_end > pos + entry_len:
        name_end = pos + entry_len
    name = toc_data[name_start:name_end].decode('utf-8', errors='replace')
    entries.append((name, type_code, data_offset, comp_size, uncomp_size, is_comp))
    if entry_len < 19:
        break
    pos += entry_len

print(f"\nFound {len(entries)} TOC entries:")
for name, tc, off, cs, us, comp in entries:
    abs_off = archive_start + off
    print(f"  type={tc}  comp={comp}  offset={abs_off}  comp={cs}  uncomp={us}  name={name}")

# Find PYZ entry
pyz_entries = [e for e in entries if e[1] == 'z']
if not pyz_entries:
    print("\nNo PYZ entry found!")
else:
    name, tc, off, cs, us, comp = pyz_entries[0]
    abs_off = archive_start + off
    pyz_raw = data[abs_off:abs_off + cs]
    print(f"\nPYZ entry: name={name}")
    print(f"  compressed={comp}  comp_size={cs}  uncomp_size={us}")
    print(f"  absolute_offset={abs_off}")
    print(f"  first 32 bytes hex: {pyz_raw[:32].hex()}")
    print(f"  first 32 bytes ascii: {pyz_raw[:32]}")

    # Check if it starts with ZlibArchive magic
    zlib_magic = b"ZlibArchive \x00\x00\x00\x01"
    if pyz_raw[:16] == zlib_magic:
        print(f"  ZlibArchive magic: FOUND (correct)")
    else:
        print(f"  ZlibArchive magic: NOT FOUND at start")
        print(f"  Expected: {zlib_magic.hex()}")
        print(f"  Got:      {pyz_raw[:16].hex()}")

    # Try to read the PYZ TOC
    if comp:
        print(f"\n  PYZ data is marked as compressed, trying decompress...")
        try:
            pyz_decomp = zlib.decompress(pyz_raw)
            print(f"  Decompressed: {len(pyz_decomp)} bytes")
            print(f"  Decompressed first 32 hex: {pyz_decomp[:32].hex()}")
            if pyz_decomp[:16] == zlib_magic:
                print(f"  ZlibArchive magic in decompressed: FOUND")
                pyz_raw = pyz_decomp
            else:
                print(f"  ZlibArchive magic in decompressed: NOT FOUND")
        except Exception as e:
            print(f"  Decompress failed: {e}")

    # Try reading PYZ TOC regardless
    print(f"\n  Attempting PYZ TOC read...")
    try:
        if pyz_raw[:16] == zlib_magic:
            toc_len_pos = len(zlib_magic)
            pyz_toc_len = struct.unpack(">I", pyz_raw[toc_len_pos:toc_len_pos+4])[0]
            print(f"  PYZ TOC length: {pyz_toc_len}")
            pyz_toc_compressed = pyz_raw[toc_len_pos+4:toc_len_pos+4+pyz_toc_len]
            print(f"  PYZ TOC compressed bytes: {len(pyz_toc_compressed)}")
            pyz_toc_raw = zlib.decompress(pyz_toc_compressed)
            print(f"  PYZ TOC decompressed: {len(pyz_toc_raw)} bytes")

            import marshal
            toc = marshal.loads(pyz_toc_raw)
            print(f"  PYZ TOC type: {type(toc).__name__}")

            if isinstance(toc, dict):
                print(f"  PYZ TOC has {len(toc)} entries (dict)")
                src_keys = sorted(k for k in toc if k.startswith("src."))
                print(f"  src.* modules: {len(src_keys)}")
                for k in src_keys[:30]:
                    print(f"    {k}")
                if len(src_keys) > 30:
                    print(f"    ... and {len(src_keys)-30} more")
            elif isinstance(toc, (list, tuple)):
                print(f"  PYZ TOC has {len(toc)} entries (list)")
                names = set()
                for entry in toc:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                        if isinstance(entry[0], str):
                            names.add(entry[0])
                src_names = sorted(n for n in names if n.startswith("src."))
                print(f"  src.* modules: {len(src_names)}")
                for n in src_names[:30]:
                    print(f"    {n}")
            else:
                print(f"  Unexpected TOC type: {type(toc)}")
                print(f"  First element: {repr(toc)[:200]}")
        else:
            print(f"  Cannot read PYZ TOC — no ZlibArchive magic")
    except Exception as e:
        print(f"  PYZ TOC read failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

print("\nDone.")