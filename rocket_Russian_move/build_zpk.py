import os
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEVICE_DIR = BASE / "_zpk_extract" / "device"
APP_SIDE_ZIP = BASE / "_zpk_extract" / "app-side.zip"
DEVICE_ZIP = BASE / "_zpk_build" / "device.zip"
OUTPUT_ZPK = BASE / "rocket_Russian_move.zpk"
BUILD_DIR = BASE / "_zpk_build"


def zip_dir(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            dirs.sort()
            files.sort()
            for name in files:
                full_path = Path(root) / name
                arcname = full_path.relative_to(source_dir).as_posix()
                zf.write(full_path, arcname)


def build_zpk() -> None:
    if not DEVICE_DIR.is_dir():
        raise SystemExit(f"Missing device dir: {DEVICE_DIR}")
    if not APP_SIDE_ZIP.is_file():
        raise SystemExit(f"Missing app-side.zip: {APP_SIDE_ZIP}")

    zip_dir(DEVICE_DIR, DEVICE_ZIP)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZPK.exists():
        OUTPUT_ZPK.unlink()

    with zipfile.ZipFile(OUTPUT_ZPK, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(APP_SIDE_ZIP, "app-side.zip")
        zf.write(DEVICE_ZIP, "device.zip")

    print(f"Built: {OUTPUT_ZPK}")
    print(f"Size: {OUTPUT_ZPK.stat().st_size} bytes")


if __name__ == "__main__":
    build_zpk()
