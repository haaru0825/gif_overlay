"""크로스 플랫폼 빌드 스크립트: Windows(exe) / Linux(바이너리) / macOS(.app)

사용법:  python build.py
결과물:  dist/ 폴더 (Windows: GifOverlay.exe, Linux: GifOverlay, macOS: GifOverlay.app)

같은 폴더에 icon.ico가 있으면 exe 아이콘(Windows)과 트레이 아이콘(전 플랫폼)으로 사용한다.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)


def run(cmd):
    print(">", " ".join(map(str, cmd)))
    subprocess.check_call(cmd)


def main():
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller", "-r", "requirements.txt"])

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--windowed", "--name", "GifOverlay"]
    # macOS는 onefile+windowed 조합이 deprecated라 .app(onedir)로 만든다
    if sys.platform != "darwin":
        cmd.append("--onefile")

    icon = HERE / "icon.ico"
    if icon.exists():
        print("icon.ico 사용")
        cmd += ["--add-data", f"{icon}{os.pathsep}."]  # 트레이 아이콘용으로 번들
        if sys.platform == "win32":
            cmd += ["--icon", str(icon)]               # exe 파일 아이콘
    else:
        print("no icon.ico")

    cmd.append("gif_overlay.py")
    run(cmd)
    print("\ndone! check dist/ folder.")


if __name__ == "__main__":
    main()
