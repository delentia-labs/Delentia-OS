import os
import zlib
import struct

def write_png(filename, w, h):
    # Header
    png = bytearray(b'\x89PNG\r\n\x1a\n')
    
    # IHDR chunk
    # Width (4 bytes), Height (4 bytes), Bit depth (8), Color type (6 - RGBA), Compression (0), Filter (0), Interlace (0)
    ihdr_data = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    ihdr = b'IHDR' + ihdr_data
    png += struct.pack('>I', len(ihdr_data)) + ihdr + struct.pack('>I', zlib.crc32(ihdr))
    
    # IDAT chunk (indigo pixels #3b6fe8)
    pixel = b'\x3b\x6f\xe8\xff'
    row = b'\x00' + (pixel * w)
    img_data = row * h
    idat_data = zlib.compress(img_data)
    idat = b'IDAT' + idat_data
    png += struct.pack('>I', len(idat_data)) + idat + struct.pack('>I', zlib.crc32(idat))
    
    # IEND chunk
    iend = b'IEND'
    png += struct.pack('>I', 0) + iend + struct.pack('>I', zlib.crc32(iend))
    
    return bytes(png)

def write_ico(filename, png_data, w, h):
    header = struct.pack('<HHH', 0, 1, 1)
    entry = struct.pack('<BBBBHHII', w if w < 256 else 0, h if h < 256 else 0, 0, 0, 1, 32, len(png_data), 22)
    with open(filename, 'wb') as f:
        f.write(header + entry + png_data)

def write_icns(filename, png_data):
    chunk_type = b'ic07' # 128x128 PNG format
    chunk_size = 8 + len(png_data)
    chunk = chunk_type + struct.pack('>I', chunk_size) + png_data
    
    file_size = 8 + len(chunk)
    header = b'icns' + struct.pack('>I', file_size)
    with open(filename, 'wb') as f:
        f.write(header + chunk)

def main():
    icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
    os.makedirs(icons_dir, exist_ok=True)
    
    # Generate PNGs
    png_32 = write_png(os.path.join(icons_dir, '32x32.png'), 32, 32)
    with open(os.path.join(icons_dir, '32x32.png'), 'wb') as f:
        f.write(png_32)
        
    png_128 = write_png(os.path.join(icons_dir, '128x128.png'), 128, 128)
    with open(os.path.join(icons_dir, '128x128.png'), 'wb') as f:
        f.write(png_128)
        
    png_256 = write_png(os.path.join(icons_dir, '128x128@2x.png'), 256, 256)
    with open(os.path.join(icons_dir, '128x128@2x.png'), 'wb') as f:
        f.write(png_256)
        
    # Generate ICO & ICNS
    write_ico(os.path.join(icons_dir, 'icon.ico'), png_128, 128, 128)
    write_icns(os.path.join(icons_dir, 'icon.icns'), png_128)
    
    print("Successfully generated all required icons in src-tauri/icons!")

if __name__ == '__main__':
    main()
