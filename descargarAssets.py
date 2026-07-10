# Descarga assets USD (con texturas/dependencias) del bucket S3 publico de NVIDIA Omniverse.
# Solo usa la libreria estandar de Python. Uso:
#   python descargar_assets.py
#
# Los archivos se guardan en DEST_DIR manteniendo la estructura de carpetas del bucket.

import os
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

BUCKET_URL = "https://omniverse-content-production.s3-us-west-2.amazonaws.com"

# Carpeta local de destino (cambiala si quieres)
DEST_DIR = r"D:\Robotics_AI\5.OpenUSD\assets"

# Prefijos (carpetas del bucket) a descargar completos
PREFIXES = [
    "Assets/DigitalTwin/Assets/Warehouse/Shipping/Cardboard_Boxes/Flat_A/",
    "Assets/DigitalTwin/Assets/Warehouse/Equipment/Hand_Trucks/Convertible_Aluminum_A/",
]

NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_keys(prefix):
    """Lista todas las claves (archivos) bajo un prefijo, con paginacion."""
    keys = []
    token = None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        url = f"{BUCKET_URL}/?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=60) as r:
            root = ET.fromstring(r.read())
        for c in root.findall("s3:Contents", NS):
            key = c.find("s3:Key", NS).text
            size = int(c.find("s3:Size", NS).text)
            if size > 0:  # ignora "carpetas" vacias
                keys.append((key, size))
        truncated = root.find("s3:IsTruncated", NS)
        if truncated is not None and truncated.text == "true":
            token = root.find("s3:NextContinuationToken", NS).text
        else:
            break
    return keys


def download(key, size):
    local_path = os.path.join(DEST_DIR, key.replace("/", os.sep))
    if os.path.exists(local_path) and os.path.getsize(local_path) == size:
        print(f"  [ok] ya existe: {key}")
        return
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    url = f"{BUCKET_URL}/{urllib.parse.quote(key)}"
    print(f"  [->] {key} ({size/1024:.0f} KB)")
    tmp = local_path + ".part"
    try:
        with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
            while chunk := r.read(1024 * 256):
                f.write(chunk)
        os.replace(tmp, local_path)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f"  [ERROR] {key}: {e}", file=sys.stderr)


def main():
    total = 0
    for prefix in PREFIXES:
        print(f"\nListando: {prefix}")
        keys = list_keys(prefix)
        print(f"  {len(keys)} archivos encontrados")
        for key, size in keys:
            download(key, size)
        total += len(keys)
    print(f"\nListo. {total} archivos en: {DEST_DIR}")


if __name__ == "__main__":
    main()
