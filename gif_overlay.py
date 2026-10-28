"""GIF Overlay - 화면 위에 GIF를 띄우고, 클릭/키 입력은 아래 창으로 통과시킨다.

Windows / Linux(X11, Wayland, 타일링 WM 포함) / macOS 지원.
PySide6가 없으면 처음 실행할 때 자동으로 설치한다. (자세한 내용은 README.md)

실행:  python gif_overlay.py [a.gif b.gif ...] [--edit] [--native-wayland]
       인자가 없으면 저장된 설정을 불러오고, 저장된 게 없으면 파일 선택창을 띄운다.
조작:  시스템 트레이 아이콘 우클릭 (편집 모드 / GIF 추가 / 크기 / 투명도 / 제거 / 종료)
       Linux에서 트레이가 없으면: pkill -USR1 -f gif_overlay.py  로 편집 모드 토글
"""
import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

REQUIRED_PACKAGES = {"PySide6": "PySide6"}  # {import 이름: pip 패키지 이름}
APP_NAME = "gif_overlay"


# --------------------------------------------------------------------------
# 경로 / 설정 위치
# --------------------------------------------------------------------------
def config_dir() -> Path:
    if sys.platform == "win32":
        return Path.home()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def config_path() -> Path:
    if sys.platform == "win32":
        return Path.home() / ".gif_overlay.json"  # 기존 버전과 호환
    return config_dir() / "config.json"


CONFIG_PATH = config_path()


# --------------------------------------------------------------------------
# 패키지 자동 설치
# --------------------------------------------------------------------------
def _notify(title, text):
    """콘솔창이 없어도(pythonw) 보이도록 Windows에선 메시지 박스를 쓴다."""
    print(f"[{title}] {text}")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
        except Exception:
            pass


def _externally_managed() -> bool:
    """Debian/Ubuntu/Arch/Fedora 등: 시스템 파이썬에 pip 설치를 막아둔 환경(PEP 668)."""
    import sysconfig
    return (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").exists()


def _bootstrap_venv(missing):
    """시스템 파이썬이 pip 설치를 막아둔 경우: 전용 venv를 만들어 설치한 뒤 그 파이썬으로 다시 실행."""
    venv_dir = config_dir() / "venv"
    vpy = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    if not vpy.exists():
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        if subprocess.run([sys.executable, "-m", "venv", str(venv_dir)]).returncode != 0:
            _notify("GIF Overlay",
                    "venv를 만들 수 없어요. 배포판에서 venv 패키지를 먼저 설치해 주세요.\n"
                    "예) Debian/Ubuntu: sudo apt install python3-venv\n"
                    "또는 직접 설치: pipx install PySide6 / 배포판 패키지(python-pyside6) 사용")
            sys.exit(1)

    have = subprocess.run([str(vpy), "-c", "import PySide6"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not have:
        _notify("GIF Overlay", "필요한 패키지를 설치합니다 (처음 한 번만): " + ", ".join(missing))
        cmd = [str(vpy), "-m", "pip", "install", "--disable-pip-version-check"] + missing
        if subprocess.run(cmd).returncode != 0:
            _notify("GIF Overlay", "패키지 설치에 실패했어요. 인터넷 연결을 확인해 주세요.")
            sys.exit(1)

    os.execv(str(vpy), [str(vpy)] + sys.argv)  # 이 프로세스를 venv 파이썬으로 교체


def ensure_packages():
    """필요한 패키지가 없으면 자동 설치한다. (PyInstaller 빌드본은 이미 포함되어 건너뜀)"""
    if getattr(sys, "frozen", False):
        return
    import importlib.util

    missing = [pip for mod, pip in REQUIRED_PACKAGES.items()
               if importlib.util.find_spec(mod) is None]
    if not missing:
        return

    in_venv = sys.prefix != sys.base_prefix
    if sys.platform != "win32" and not in_venv and _externally_managed():
        _bootstrap_venv(missing)  # 성공하면 여기로 돌아오지 않는다
        return

    _notify("GIF Overlay", "필요한 패키지를 설치합니다: " + ", ".join(missing)
            + "\n(처음 한 번만, 1~2분 걸릴 수 있어요. 확인을 누르고 잠시 기다려 주세요.)")
    # pip 자체가 없는 환경 대비
    subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    # 일반 설치 -> 권한 문제면 --user로 재시도
    ok = (subprocess.run(base + missing).returncode == 0
          or subprocess.run(base + ["--user"] + missing).returncode == 0)
    if not ok:
        _notify("GIF Overlay", "패키지 설치에 실패했어요.\n인터넷 연결을 확인하거나 직접 설치해 주세요:\n"
                f"pip install {' '.join(missing)}")
        sys.exit(1)
    importlib.invalidate_caches()


ensure_packages()

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QAction, QColor, QGuiApplication, QIcon, QMovie, QPainter, QPen,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFileDialog,
    QLabel,
    QMenu,
    QStyle,
    QSystemTrayIcon,
)


# --------------------------------------------------------------------------
# 플랫폼별 창 설정
# --------------------------------------------------------------------------
def choose_qt_platform(native_wayland: bool):
    """Linux Wayland 세션에서는 기본적으로 XWayland(xcb)로 띄운다.

    네이티브 Wayland에서는 앱이 창 위치를 정하거나 '항상 위'를 보장할 수 없어서,
    타일링 WM(sway, Hyprland 등)에서도 의도대로 뜨게 하려면 xcb 쪽이 가장 확실하다.
    --native-wayland 를 주면 네이티브로 실행하고, WM 규칙으로 floating 처리해야 한다.
    """
    if not sys.platform.startswith("linux") or "QT_QPA_PLATFORM" in os.environ:
        return
    if native_wayland:
        return
    if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def window_flags(edit_mode: bool):
    flags = (
        Qt.FramelessWindowHint
        | Qt.WindowStaysOnTopHint
        | Qt.Tool                      # 작업표시줄/독에 안 보이게
        | Qt.WindowDoesNotAcceptFocus  # 키보드 포커스를 뺏지 않음
    )
    if QGuiApplication.platformName() == "xcb":
        # X11: WM이 이 창을 아예 관리하지 않게 한다 -> 타일링 WM이 타일로 잡지 않고,
        # 내가 정한 좌표에 그대로 뜬다. (i3, bspwm, awesome, dwm ...)
        flags |= Qt.X11BypassWindowManagerHint
    if not edit_mode:
        flags |= Qt.WindowTransparentForInput  # 마우스/키 입력을 아래 창으로 통과
    return flags


class GifOverlay(QLabel):
    """GIF 하나를 보여주는 투명 오버레이 창."""

    changed = Signal()  # 위치/크기/투명도가 바뀌면 알림 (저장용)

    def __init__(self, path, x=100, y=100, scale=1.0, opacity=1.0):
        super().__init__()
        self.path = str(path)
        self.scale = scale
        self.opacity_value = opacity
        self.edit_mode = False
        self._drag_offset = QPoint()

        self.movie = QMovie(self.path)
        self.valid = self.movie.isValid()
        if not self.valid:
            return

        # 원본 크기를 알려면 첫 프레임을 한 번 읽어야 한다
        self.movie.jumpToFrame(0)
        self.base_size = self.movie.currentPixmap().size()
        self.setMovie(self.movie)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        mac_attr = getattr(Qt, "WA_MacAlwaysShowToolWindow", None)
        if sys.platform == "darwin" and mac_attr is not None:
            self.setAttribute(mac_attr)  # 앱이 비활성이어도 창을 숨기지 않음
        self.apply_scale()
        self.setWindowOpacity(self.opacity_value)
        self.move(x, y)
        self.set_edit_mode(False)
        self.movie.start()

    # ---- 크기 / 투명도 ----
    def apply_scale(self):
        w = max(1, int(self.base_size.width() * self.scale))
        h = max(1, int(self.base_size.height() * self.scale))
        self.movie.setScaledSize(QSize(w, h))
        self.setFixedSize(w, h)

    def set_scale(self, scale):
        self.scale = max(0.1, min(5.0, scale))
        self.apply_scale()
        self.changed.emit()

    def set_opacity(self, opacity):
        self.opacity_value = opacity
        self.setWindowOpacity(opacity)
        self.changed.emit()

    # ---- 편집 모드 / 클릭 통과 ----
    def set_edit_mode(self, on):
        self.edit_mode = on
        pos = self.pos()
        self.setWindowFlags(window_flags(on))  # 플래그를 바꾸면 창이 숨겨지므로
        self.show()                            # 다시 보여준다
        self.move(pos)                         # 플랫폼에 따라 위치가 초기화될 수 있어 복원
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.edit_mode:
            painter = QPainter(self)
            painter.setPen(QPen(QColor("#ff4081"), 2, Qt.DashLine))
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

    # ---- 편집 모드에서만 마우스 입력을 받는다 (드래그 이동 / 휠 크기) ----
    def mousePressEvent(self, event):
        if self.edit_mode and event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.edit_mode and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if self.edit_mode and event.button() == Qt.LeftButton:
            self.changed.emit()

    def wheelEvent(self, event):
        if self.edit_mode:
            factor = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
            self.set_scale(self.scale * factor)

    def to_dict(self):
        return {
            "path": self.path,
            "x": self.x(),
            "y": self.y(),
            "scale": round(self.scale, 3),
            "opacity": self.opacity_value,
        }


class Controller:
    """오버레이 목록 + 트레이 메뉴 + 설정 저장을 관리한다."""

    def __init__(self, app):
        self.app = app
        self.overlays = []
        self.edit_mode = False

        # icon.ico가 있으면(빌드본에는 번들됨) 트레이 아이콘으로 쓰고, 없으면 기본 아이콘
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        icon_file = base_dir / "icon.ico"
        icon = QIcon(str(icon_file)) if icon_file.exists() else QIcon()
        if icon.isNull():
            icon = app.style().standardIcon(QStyle.SP_MediaPlay)
        self.tray = QSystemTrayIcon(icon, app)
        self.tray.setToolTip("GIF Overlay")
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.show()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("[GIF Overlay] 시스템 트레이를 찾을 수 없어요 (waybar/i3bar 등에 트레이 모듈이 필요).\n"
                  "  - 편집 모드 토글:  pkill -USR1 -f gif_overlay.py   (WM 단축키에 걸어두세요)\n"
                  "  - 종료:            pkill -f gif_overlay.py")

        # 다른 '항상 위' 창에 가려지는 걸 막기 위해 주기적으로 맨 위로 올린다
        self.raise_timer = QTimer()
        self.raise_timer.timeout.connect(self.raise_all)
        self.raise_timer.start(3000)

    def raise_all(self):
        if not self.edit_mode:
            for o in self.overlays:
                o.raise_()

    # ---- GIF 추가/제거 ----
    def add_gif(self, path, **kwargs):
        n = len(self.overlays)
        kwargs.setdefault("x", 100 + 40 * n)
        kwargs.setdefault("y", 100 + 40 * n)
        overlay = GifOverlay(path, **kwargs)
        if not overlay.valid:
            msg = f"열 수 없는 파일: {Path(path).name}"
            print("[GIF Overlay]", msg)
            self.tray.showMessage("GIF 오류", msg)
            return None
        overlay.changed.connect(self.save)
        if self.edit_mode:
            overlay.set_edit_mode(True)
        self.overlays.append(overlay)
        return overlay

    def remove_gif(self, overlay):
        overlay.movie.stop()
        overlay.close()
        overlay.deleteLater()
        self.overlays.remove(overlay)
        self.save()
        self.rebuild_menu()

    def prompt_add(self):
        paths, _ = QFileDialog.getOpenFileNames(None, "GIF 선택", "", "GIF (*.gif)")
        for p in paths:
            self.add_gif(p)
        self.save()
        self.rebuild_menu()

    # ---- 편집 모드 ----
    def toggle_edit(self, on):
        self.edit_mode = on
        for o in self.overlays:
            o.set_edit_mode(on)
        if on:
            self.tray.showMessage("편집 모드", "드래그: 이동 / 마우스 휠: 크기 조절")
        else:
            self.save()

    def toggle_edit_from_signal(self):
        """SIGUSR1용: 트레이가 없는 환경에서 WM 단축키로 편집 모드를 켜고 끈다."""
        self.toggle_edit(not self.edit_mode)
        self.rebuild_menu()

    # ---- 저장/불러오기 ----
    def save(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = [o.to_dict() for o in self.overlays]
            CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            print("설정 저장 실패:", e)

    def load(self):
        try:
            items = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in items:
            if Path(item.get("path", "")).exists():
                self.add_gif(
                    item["path"],
                    x=item.get("x", 100),
                    y=item.get("y", 100),
                    scale=item.get("scale", 1.0),
                    opacity=item.get("opacity", 1.0),
                )

    # ---- 트레이 메뉴 ----
    def rebuild_menu(self):
        self.menu.clear()

        edit_action = QAction("편집 모드 (드래그 이동 / 휠 크기)", self.menu)
        edit_action.setCheckable(True)
        edit_action.setChecked(self.edit_mode)
        edit_action.toggled.connect(self.toggle_edit)
        self.menu.addAction(edit_action)

        add_action = QAction("GIF 추가...", self.menu)
        add_action.triggered.connect(self.prompt_add)
        self.menu.addAction(add_action)

        if self.overlays:
            self.menu.addSeparator()
        for overlay in self.overlays:
            sub = self.menu.addMenu(Path(overlay.path).name)

            size_menu = sub.addMenu("크기")
            for pct in (25, 50, 100, 150, 200, 300):
                a = size_menu.addAction(f"{pct}%")
                a.triggered.connect(lambda _=False, o=overlay, p=pct: o.set_scale(p / 100))

            op_menu = sub.addMenu("투명도")
            for pct in (100, 80, 60, 40, 20):
                a = op_menu.addAction(f"{pct}%")
                a.triggered.connect(lambda _=False, o=overlay, p=pct: o.set_opacity(p / 100))

            rm = sub.addAction("제거")
            rm.triggered.connect(lambda _=False, o=overlay: self.remove_gif(o))

        self.menu.addSeparator()
        quit_action = QAction("종료", self.menu)
        quit_action.triggered.connect(self.quit)
        self.menu.addAction(quit_action)

    def quit(self):
        self.save()
        self.tray.hide()
        self.app.quit()


def main():
    parser = argparse.ArgumentParser(description="화면 위에 GIF를 띄우는 클릭 통과 오버레이")
    parser.add_argument("gifs", nargs="*", help="재생할 GIF 파일들")
    parser.add_argument("--edit", action="store_true", help="편집 모드로 시작 (드래그 이동 / 휠 크기)")
    parser.add_argument("--native-wayland", action="store_true",
                        help="(Linux) XWayland 대신 네이티브 Wayland로 실행. WM 규칙으로 floating 처리 필요")
    args, qt_args = parser.parse_known_args()

    choose_qt_platform(args.native_wayland)

    app = QApplication([sys.argv[0]] + qt_args)
    app.setQuitOnLastWindowClosed(False)
    # WM 규칙에서 쓸 이름: X11 class / Wayland app_id = "gif_overlay"
    app.setApplicationName(APP_NAME)
    QGuiApplication.setDesktopFileName(APP_NAME)

    ctrl = Controller(app)

    if args.gifs:
        for p in args.gifs:
            ctrl.add_gif(p)
        ctrl.save()
    else:
        ctrl.load()
        if not ctrl.overlays:
            ctrl.prompt_add()
            if not ctrl.overlays:
                return
    if args.edit:
        ctrl.toggle_edit(True)
    ctrl.rebuild_menu()

    # 터미널 Ctrl+C / kill 처리 (이벤트 루프가 돌아야 시그널이 처리되므로 타이머를 둔다)
    signal.signal(signal.SIGINT, lambda *_: ctrl.quit())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: ctrl.quit())
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, lambda *_: ctrl.toggle_edit_from_signal())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(500)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
