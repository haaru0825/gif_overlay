"""GIF 오버레이 v2 (Windows 기준)

- GIF를 화면 맨 위에 띄우고, 클릭/키 입력은 아래 창으로 통과시킨다.
- 여러 GIF를 동시에 띄울 수 있다.
- 편집 모드에서 마우스로 드래그해 위치를, 휠로 크기를 바꿀 수 있다.
- 위치/크기/투명도는 자동 저장되어 다음 실행 때 그대로 복원된다.

설치:  필요 없음 (PySide6가 없으면 실행 시 자동 설치됨)
실행:  python gif_overlay.py a.gif b.gif     (인자 없으면 저장된 설정을 불러옴)
exe:   build_exe.bat 더블클릭 -> dist/GifOverlay.exe 생성
       pythonw gif_overlay.py                (콘솔창 없이 실행)

조작: 시스템 트레이(작업표시줄 오른쪽 아래) 아이콘 우클릭
  - 편집 모드: 켜면 점선 테두리가 생기고 드래그(이동) / 마우스 휠(크기) 가능
  - GIF 추가 / 각 GIF별 크기·투명도·제거 / 종료
"""
import json
import signal
import subprocess
import sys
from pathlib import Path

REQUIRED_PACKAGES = {"PySide6": "PySide6"}  # {import 이름: pip 패키지 이름}


def _notify(title, text):
    """콘솔창이 없어도(pythonw) 보이도록 Windows에선 메시지 박스를 쓴다."""
    print(f"[{title}] {text}")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
        except Exception:
            pass


def ensure_packages():
    """필요한 패키지가 없으면 pip로 자동 설치한다. (exe로 빌드된 경우엔 이미 포함되어 건너뜀)"""
    if getattr(sys, "frozen", False):
        return
    import importlib.util

    missing = [pip for mod, pip in REQUIRED_PACKAGES.items()
               if importlib.util.find_spec(mod) is None]
    if not missing:
        return

    _notify("GIF 오버레이", "필요한 패키지를 설치합니다: " + ", ".join(missing)
            + "\n(처음 한 번만, 1~2분 걸릴 수 있어요. 확인을 누르고 잠시 기다려 주세요.)")
    # pip 자체가 없는 환경 대비
    subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    # 일반 설치 -> 권한 문제면 --user로 재시도
    ok = (subprocess.run(base + missing).returncode == 0
          or subprocess.run(base + ["--user"] + missing).returncode == 0)
    if not ok:
        _notify("GIF 오버레이", "패키지 설치에 실패했어요.\n인터넷 연결을 확인하거나 직접 설치해 주세요:\n"
                f"pip install {' '.join(missing)}")
        sys.exit(1)
    importlib.invalidate_caches()


ensure_packages()

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QMovie, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMenu,
    QStyle,
    QSystemTrayIcon,
)

CONFIG_PATH = Path.home() / ".gif_overlay.json"


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
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # 포커스를 뺏지 않음
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
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        if not on:
            flags |= Qt.WindowTransparentForInput  # 입력을 아래 창으로 통과
        self.setWindowFlags(flags)  # 플래그를 바꾸면 창이 숨겨지므로
        self.show()                 # 다시 보여준다
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

        self.tray = QSystemTrayIcon(app.style().standardIcon(QStyle.SP_MediaPlay), app)
        self.tray.setToolTip("GIF 오버레이")
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.show()

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
            self.tray.showMessage("GIF 오류", f"열 수 없는 파일: {Path(path).name}")
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

    # ---- 저장/불러오기 ----
    def save(self):
        try:
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
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    ctrl = Controller(app)

    paths = sys.argv[1:]
    if paths:
        for p in paths:
            ctrl.add_gif(p)
        ctrl.save()
    else:
        ctrl.load()
        if not ctrl.overlays:
            ctrl.prompt_add()
            if not ctrl.overlays:
                return
    ctrl.rebuild_menu()

    # 터미널 Ctrl+C 처리 (이벤트 루프가 돌아야 시그널이 처리되므로 타이머를 둔다)
    signal.signal(signal.SIGINT, lambda *_: ctrl.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(500)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
