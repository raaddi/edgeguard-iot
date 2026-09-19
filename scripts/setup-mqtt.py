"""Extract pinned official Mosquitto binaries locally on Windows; install no service."""

from hashlib import sha256
from pathlib import Path
import platform
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools"
DOWNLOADS = (
    ("7zr.exe", "https://github.com/ip7z/7zip/releases/download/26.03/7zr.exe",
     "ad4c82fadcbdf93c03b4fc440f300509c7d60c5c2f4d183e35d9d70d6957037d"),
    ("7z2603-x64.exe", "https://github.com/ip7z/7zip/releases/download/26.03/7z2603-x64.exe",
     "0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd"),
    ("mosquitto-2.1.2-installer.exe",
     "https://mosquitto.org/files/binary/win64/mosquitto-2.1.2-install-windows-x64.exe",
     "58008ad7a22ada0b4073afa415801746e027c5f583e4fa52d0f4e9193b98d6aa"),
)


def main():
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("This helper supports Windows x64. On Linux install Mosquitto from your distribution.")
    TOOLS.mkdir(exist_ok=True)
    for name, url, expected in DOWNLOADS:
        target = TOOLS / name
        if target.exists():
            data = target.read_bytes()
        else:
            print(f"Download: {name}", flush=True)
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024 or sha256(data).hexdigest() != expected:
            raise SystemExit(f"Checksum mismatch: {name}; nothing will be executed.")
        if not target.exists():
            target.write_bytes(data)
    commands = [
        [str(TOOLS / "7zr.exe"), "x", str(TOOLS / "7z2603-x64.exe"), f"-o{TOOLS / '7zip-portable'}", "-y"],
        [str(TOOLS / "7zip-portable/7z.exe"), "x", str(TOOLS / "mosquitto-2.1.2-installer.exe"),
         f"-o{TOOLS / 'mosquitto'}", "-y"],
    ]
    for command in commands:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    print(f"Ready: {TOOLS / 'mosquitto/mosquitto.exe'}")


if __name__ == "__main__":
    main()
