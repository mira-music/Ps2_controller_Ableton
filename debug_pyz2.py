"""Temporary diagnostic — probes the new PYZ format. Delete after use."""
from pathlib import Path
import struct
import zlib
import marshal

data = Path('dist/FX_Machine/FX_Machine.exe').read_bytes()

# Known values from previous debug
archive_start = 342528
pyz_offset = 369039
pyz_size = 2598963

pyz_data = data[pyz_offset:pyz_offset + pyz_size]

print(f"PYZ total size: {len(pyz_data)} bytes")
print(f"First 32 bytes hex: {pyz_data[:32].hex()}")
print()

# The new PYZ format starts with "PYZ\x00" + python magic (8 bytes)
# Then possibly a header, then zlib-compressed marshal'd TOC

# Try to find where zlib data starts by scanning for the zlib magic (78 9c)
for start_offset in range(8, min(64, len(pyz_data))):
    if pyz_data[start_offset:start_offset+2] in (b'\x78\x9c', b'\x78\x01', b'\x78\xda'):
        print(f"Found zlib magic at PYZ offset {start_offset}: {pyz_data[start_offset:start_offset+2].hex()}")

        # Everything from here to the end MIGHT be one big zlib stream
        # containing all the modules. Or it might be structured differently.
        # Let's try decompressing from this offset to see what we get.
        compressed_blob = pyz_data[start_offset:]
        try:
            decompressed = zlib.decompress(compressed_blob)
            print(f"  Decompressed: {len(decompressed)} bytes")
            print(f"  First 64 bytes hex: {decompressed[:64].hex()}")
            print(f"  First 64 bytes repr: {decompressed[:64]!r}")

            # Try to unmarshal it
            try:
                obj = marshal.loads(decompressed)
                obj_type = type(obj).__name__
                print(f"\n  Marshal loads succeeded! Type: {obj_type}")

                if isinstance(obj, dict):
                    print(f"  Dict has {len(obj)} keys")
                    src_keys = sorted(k for k in obj if isinstance(k, str) and k.startswith("src."))
                    print(f"  src.* keys: {len(src_keys)}")
                    for k in src_keys[:30]:
                        print(f"    {k}")
                    if len(src_keys) > 30:
                        print(f"    ... and {len(src_keys) - 30} more")

                    # Show some non-src keys too
                    other_keys = sorted(k for k in obj if isinstance(k, str) and not k.startswith("src."))[:10]
                    print(f"\n  First 10 non-src keys:")
                    for k in other_keys:
                        print(f"    {k}")

                elif isinstance(obj, (list, tuple)):
                    print(f"  List/tuple has {len(obj)} entries")
                    if len(obj) > 0:
                        print(f"  First entry type: {type(obj[0]).__name__}")
                        print(f"  First entry: {obj[0]!r}")
                else:
                    print(f"  Unexpected type. repr[:200]: {repr(obj)[:200]}")

            except Exception as e:
                print(f"\n  Marshal loads failed: {e}")
                # The decompressed data might not be a single marshal object
                # It might be individual module .pyc files concatenated
                # Try to find module names by string search
                import re
                names = set()
                for m in re.findall(rb'([a-zA-Z_][a-zA-Z0-9_.]{3,60})', decompressed):
                    try:
                        s = m.decode('ascii')
                        if s.startswith('src.'):
                            names.add(s)
                    except:
                        pass
                src_names = sorted(names)
                print(f"  String search found {len(src_names)} src.* names:")
                for n in src_names[:30]:
                    print(f"    {n}")

        except zlib.error as e:
            print(f"  Decompression from offset {start_offset} failed: {e}")
            # Try with a wbits variation
            for wbits in [-15, 15, -9, 9, 31, 47]:
                try:
                    dec = zlib.decompressobj(wbits)
                    result = dec.decompress(compressed_blob[:100000])
                    print(f"  wbits={wbits}: got {len(result)} bytes")
                    break
                except:
                    pass

        print()

# Also try: maybe the PYZ contains individual entries, not one big blob
# The header might specify a TOC length after the python magic
print("\nTrying alternative header interpretations:")
print(f"  Bytes 8-11 as uint32 BE: {struct.unpack_from('>I', pyz_data, 8)[0]}")
print(f"  Bytes 8-11 as uint32 LE: {struct.unpack_from('<I', pyz_data, 8)[0]}")
print(f"  Bytes 12-15 as uint32 BE: {struct.unpack_from('>I', pyz_data, 12)[0]}")
print(f"  Bytes 12-15 as uint32 LE: {struct.unpack_from('<I', pyz_data, 12)[0]}")

# Try: bytes 8-11 might be the TOC length
toc_len_candidate = struct.unpack_from('>I', pyz_data, 8)[0]
print(f"\n  If bytes 8-11 ({toc_len_candidate}) is TOC length:")
print(f"  TOC would be at offset 12, length {toc_len_candidate}")
if toc_len_candidate < len(pyz_data):
    toc_blob = pyz_data[12:12 + toc_len_candidate]
    print(f"  TOC blob first 16 hex: {toc_blob[:16].hex()}")

# Another possibility: bytes 8-11 is the number of entries
entries_candidate = struct.unpack_from('>I', pyz_data, 8)[0]
print(f"\n  If bytes 8-11 ({entries_candidate}) is entry count:")
print(f"  That would mean {entries_candidate} modules bundled")

print("\nDone.")