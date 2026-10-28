# GIF Overlay

화면 위에 GIF를 띄워 놓는 가벼운 오버레이 프로그램입니다. GIF는 항상 맨 위에 떠 있지만 **클릭과 키 입력은 그대로 아래 창으로 통과**해서, 다른 창을 평소처럼 조작할 수 있어요.

*A tiny always-on-top GIF overlay with click-through. Windows, Linux (X11 / Wayland / tiling WMs) and macOS.*

## 기능

- 여러 GIF를 동시에 재생, GIF별 크기(25~300%)와 투명도 조절
- 편집 모드: 드래그로 이동, 마우스 휠로 크기 조절 (끄면 다시 클릭 통과)
- 위치/크기/투명도 자동 저장 및 복원
- PySide6가 없으면 처음 실행할 때 **자동 설치**
- 시스템 트레이 아이콘으로 모든 조작 (Windows/Linux/macOS 공통)

## 설치 / 실행

### 방법 1: 빌드된 파일 받기 (Releases)

[Releases](../../releases)에서 OS에 맞는 파일을 받아 실행하세요. Python이 필요 없습니다.

| OS | 파일 |
|----|------|
| Windows | `GifOverlay-windows.exe` |
| Linux | `GifOverlay-linux-x86_64.tar.gz` (풀고 `./GifOverlay`) |
| macOS | `GifOverlay-macos.zip` |

서명되지 않은 파일이라 Windows SmartScreen / macOS Gatekeeper가 경고를 띄울 수 있습니다. (Windows: "추가 정보 → 실행", macOS: 우클릭 → 열기)

### 방법 2: 소스로 실행

```bash
python gif_overlay.py a.gif b.gif
```

PySide6가 없으면 자동으로 설치합니다. (Debian/Ubuntu처럼 시스템 파이썬 pip 설치를 막아둔 배포판에서는 전용 venv를 만들어 설치하고, 이후 그 venv로 자동 재실행합니다. `python3-venv`가 필요할 수 있어요.)

인자 없이 실행하면 저장된 설정을 불러오고, 저장된 게 없으면 파일 선택창이 뜹니다.

| 옵션 | 설명 |
|------|------|
| `--edit` | 편집 모드로 시작 |
| `--native-wayland` | (Linux) XWayland 대신 네이티브 Wayland로 실행 |

## 사용법

시스템 트레이(알림 영역) 아이콘을 우클릭하세요.

- **편집 모드**: 점선 테두리가 생기고, 드래그로 이동 / 마우스 휠로 크기 조절
- **GIF 추가...**, GIF별 **크기 / 투명도 / 제거**
- **종료**

설정 파일 위치: Windows `~/.gif_overlay.json`, Linux `~/.config/gif_overlay/config.json`, macOS `~/Library/Application Support/gif_overlay/config.json`

## 플랫폼별 참고

### Windows
그대로 동작합니다. 전체화면 독점 모드로 도는 게임 위에는 뜨지 않고, "테두리 없는 창 모드"에서는 뜹니다.

### Linux

필요한 시스템 라이브러리 (Qt 6): Debian/Ubuntu 기준 `sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1`
(`Could not load the Qt platform plugin "xcb"` 오류가 나면 이 패키지들이 빠진 겁니다.)

**X11 (i3, bspwm, awesome, dwm 등 타일링 WM 포함)**
창에 `X11BypassWindowManagerHint`를 걸어서 WM이 이 창을 아예 관리하지 않습니다. 타일로 잡히거나 포커스를 가져가는 일 없이, 지정한 좌표에 그대로 뜹니다. 반투명 배경에는 compositor(picom 등)가 필요합니다.

**Wayland (sway, Hyprland, GNOME, KDE 등)**
기본값으로 **XWayland(xcb)** 로 실행해서 X11과 같은 방식으로 동작합니다. XWayland가 없거나 네이티브로 쓰고 싶다면 `--native-wayland`를 주고 WM 규칙으로 floating 처리하세요. 네이티브 Wayland에서는 앱이 자기 위치를 정할 수 없어서 `move` 규칙이 필요합니다. 창 이름(app_id / class)은 `gif_overlay` 입니다.

```
# sway
for_window [app_id="gif_overlay"] floating enable, sticky enable

# Hyprland
windowrulev2 = float, class:^(gif_overlay)$
windowrulev2 = pin, class:^(gif_overlay)$
windowrulev2 = noinitialfocus, class:^(gif_overlay)$
windowrulev2 = move 100 100, class:^(gif_overlay)$

# i3 (X11에서 bypass가 안 먹는 환경이라면)
for_window [class="gif_overlay"] floating enable, sticky enable
```

**트레이가 없는 환경** (waybar/i3bar에 트레이 모듈이 없는 경우)
편집 모드를 시그널로 토글할 수 있습니다. WM 단축키에 걸어 두세요.

```
# i3 / sway
bindsym $mod+g exec pkill -USR1 -f gif_overlay.py
```

종료는 `pkill -f gif_overlay.py`. 처음 위치를 잡을 때는 `--edit`로 시작해서 드래그하면 됩니다.

### macOS
best-effort 지원입니다. 전체화면 앱 위에 띄우거나 모든 데스크톱(Spaces)에 고정하는 기능은 아직 없습니다.

## 직접 빌드하기

```bash
python build.py          # 전 플랫폼 공통
build_exe.bat            # Windows: 더블클릭
./build.sh               # Linux / macOS: venv를 만들어 빌드
```

결과물은 `dist/`에 생깁니다. 같은 폴더에 `icon.ico`를 두면 exe 아이콘(Windows)과 트레이 아이콘(전 플랫폼)으로 쓰입니다.

태그(`v1.0.0` 등)를 푸시하면 GitHub Actions가 Windows / Linux / macOS용 파일을 빌드해서 Release에 자동으로 첨부합니다.

```bash
git tag v1.0.0 && git push origin v1.0.0
```

## 주의

- GIF 파일은 직접 만든 것이나 재배포가 허용된 것만 사용하세요. 이 프로그램은 PC에 있는 GIF 파일만 재생하며, 다른 앱/서비스의 콘텐츠를 가져오는 기능은 없습니다.
- 라이선스는 아직 지정하지 않았습니다. 공개 저장소로 올릴 때 `LICENSE` 파일을 추가하세요.
