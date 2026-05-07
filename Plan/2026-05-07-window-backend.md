# py-network-input Windows Backend 开发计划

## 1. 背景与目标

`py-network-input` 当前是一个轻量的局域网文字投送工具：手机或其他局域网设备通过网页/HTTP API 把文本发送到本机，本机收到后写入剪贴板，并可选自动触发粘贴快捷键或回车。

当前实现主要面向 Linux Wayland：

- 剪贴板后端：`wl-copy`
- 自动上屏：`wtype` 模拟 `Ctrl+V` / `Ctrl+Shift+V`
- 回车：`wtype key Return`
- 服务端：Python 内置 HTTP 服务
- 网页端：内置移动端 HTML 页面
- 安全机制：网页端联机确认；脚本接口使用 `NETWORK_INPUT_API_TOKEN`

本计划的目标是为项目增加 **Windows backend**，让 Windows 用户可以做到：

1. 手机网页发送文本到 Windows 主机剪贴板；
2. 可选自动粘贴到当前焦点应用；
3. 可选发送回车；
4. 保持现有 Linux Wayland 行为不破坏；
5. 保持依赖尽量轻量，优先使用 Python 标准库 + Windows API。

---

## 2. 总体设计

建议把“输入后端”抽象成统一接口，然后按平台选择不同实现。

推荐后端结构：

```text
network_input/
  input_backends.py              # 现有后端入口；可以保留兼容层
  backends/
    __init__.py
    base.py                      # 抽象接口
    wayland.py                   # 原 wl-copy / wtype 逻辑
    windows.py                   # 新增 Windows 后端
    noop.py                      # 测试或降级后端，可选
```

如果不想一次性重构太大，也可以先在现有 `input_backends.py` 中新增 Windows 实现；但长期建议拆成 `backends/` 目录，结构会更清楚。

---

## 3. 后端接口设计

新增一个通用接口，例如：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Literal


PasteMode = Literal["ctrl_v", "ctrl_shift_v"]


@dataclass(frozen=True)
class BackendResult:
    ok: bool
    message: str = ""


class InputBackend(Protocol):
    name: str

    def set_clipboard(self, text: str) -> BackendResult:
        ...

    def paste(self, mode: PasteMode = "ctrl_v") -> BackendResult:
        ...

    def press_enter(self) -> BackendResult:
        ...

    def send_text(
        self,
        text: str,
        *,
        auto_paste: bool = False,
        paste_mode: PasteMode = "ctrl_v",
        press_enter: bool = False,
    ) -> BackendResult:
        ...
```

`send_text()` 可以作为默认组合逻辑：

1. `set_clipboard(text)`
2. 如果 `auto_paste=True`，调用 `paste(paste_mode)`
3. 如果 `press_enter=True`，调用 `press_enter()`

这样 HTTP 层不需要关心平台细节。

---

## 4. Windows Backend 实现策略

### 4.1 剪贴板实现

Windows 剪贴板优先级建议：

1. 首选：`tkinter` 或 `ctypes + WinAPI`
2. 可选：`pyperclip`
3. 不建议首版依赖 PowerShell `Set-Clipboard`，因为启动慢、编码和转义容易出小问题

推荐首版直接用 `tkinter`，因为它是 Python 标准库的一部分，代码简单：

```python
def set_clipboard_tk(text: str) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    root.destroy()
```

但注意：部分精简 Python 环境可能没有 Tcl/Tk。为了更稳，可以实现 fallback：

```text
Windows clipboard strategy:
  1. try tkinter
  2. if tkinter unavailable, try ctypes WinAPI
  3. if still unavailable, return friendly error
```

如果 Codex 实现能力足够，建议直接用 `ctypes` 实现 Unicode 剪贴板，避免依赖 Tk。Windows 剪贴板应使用 `CF_UNICODETEXT`，并确保字符串以 `\0` 结尾。

---

### 4.2 键盘模拟实现

Windows 自动粘贴和回车使用 `user32.SendInput`。

需要实现的操作：

```text
Ctrl+V:
  key down Ctrl
  key down V
  key up V
  key up Ctrl

Ctrl+Shift+V:
  key down Ctrl
  key down Shift
  key down V
  key up V
  key up Shift
  key up Ctrl

Enter:
  key down Enter
  key up Enter
```

建议使用 `ctypes` 调用 WinAPI，不引入 `pyautogui` 或 `pynput`。原因：

- 依赖更少；
- 不需要额外 GUI 自动化库；
- 行为更接近系统底层；
- 更适合后续打包成单文件或 release。

需要的虚拟键码：

```python
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_RETURN = 0x0D
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
```

注意事项：

- `SendInput` 可能被 Windows UIPI 完整性级别限制。普通权限进程不能向管理员权限窗口注入输入。
- 如果目标程序以管理员权限运行，而 `py-network-input` 不是管理员权限，自动粘贴可能失败。
- 这不影响写入剪贴板。
- 文档中需要明确说明：自动上屏依赖当前焦点窗口，且可能受权限/安全软件影响。

---

## 5. 后端选择逻辑

当前 README 已经有：

```text
NETWORK_INPUT_BACKEND
```

建议扩展为：

```text
NETWORK_INPUT_BACKEND=auto
NETWORK_INPUT_BACKEND=wayland
NETWORK_INPUT_BACKEND=windows
NETWORK_INPUT_BACKEND=clipboard
NETWORK_INPUT_BACKEND=noop
```

推荐行为：

```python
def create_backend(name: str | None = None) -> InputBackend:
    backend = name or os.getenv("NETWORK_INPUT_BACKEND", "auto")

    if backend == "auto":
        if sys.platform == "win32":
            return WindowsBackend()
        if os.environ.get("WAYLAND_DISPLAY"):
            return WaylandBackend()
        return ClipboardOnlyBackend()

    if backend == "windows":
        return WindowsBackend()

    if backend == "wayland":
        return WaylandBackend()

    if backend == "clipboard":
        return ClipboardOnlyBackend()

    if backend == "noop":
        return NoopBackend()

    raise ValueError(f"Unknown backend: {backend}")
```

建议保留兼容：

- 如果用户设置 `NETWORK_INPUT_BACKEND=clipboard`，在 Windows 上只写剪贴板，不自动按键。
- 如果用户设置 `NETWORK_INPUT_BACKEND=windows` 但不是 Windows，启动时报清晰错误。
- 如果 `auto` 在 Linux 非 Wayland 环境下，可以提示暂不支持 X11 自动上屏，只支持剪贴板或 noop。

---

## 6. WindowsBackend 推荐代码骨架

```python
from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from typing import Iterable


VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_RETURN = 0x0D
VK_V = 0x56

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", INPUT_UNION),
    ]


def _keyboard_input(vk: int, *, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_KEYUP if key_up else 0
    return INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=vk,
                wScan=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=None,
            )
        ),
    )


def _send_inputs(inputs: list[INPUT]) -> None:
    user32 = ctypes.windll.user32
    count = len(inputs)
    array_type = INPUT * count
    sent = user32.SendInput(count, array_type(*inputs), ctypes.sizeof(INPUT))
    if sent != count:
        raise OSError(f"SendInput failed: sent={sent}, expected={count}")


def send_hotkey(keys: Iterable[int]) -> None:
    keys = list(keys)
    events: list[INPUT] = []

    for key in keys:
        events.append(_keyboard_input(key, key_up=False))

    for key in reversed(keys):
        events.append(_keyboard_input(key, key_up=True))

    _send_inputs(events)


def press_key(key: int) -> None:
    _send_inputs([
        _keyboard_input(key, key_up=False),
        _keyboard_input(key, key_up=True),
    ])


class WindowsBackend:
    name = "windows"

    def set_clipboard(self, text: str):
        set_clipboard_text(text)
        return BackendResult(ok=True, message="copied to Windows clipboard")

    def paste(self, mode: str = "ctrl_v"):
        if mode == "ctrl_shift_v":
            send_hotkey([VK_CONTROL, VK_SHIFT, VK_V])
        else:
            send_hotkey([VK_CONTROL, VK_V])
        return BackendResult(ok=True, message=f"sent {mode}")

    def press_enter(self):
        press_key(VK_RETURN)
        return BackendResult(ok=True, message="sent Enter")
```

上面代码是骨架，Codex 需要结合项目现有 `BackendResult`、错误处理和类型定义进行整合。

---

## 7. Windows 剪贴板 ctypes 实现建议

如果使用 WinAPI，建议实现 `CF_UNICODETEXT`：

```python
import ctypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def set_clipboard_text(text: str) -> None:
    data = text + "\0"
    encoded = data.encode("utf-16-le")
    size = len(encoded)

    h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not h_global:
        raise OSError("GlobalAlloc failed")

    locked = kernel32.GlobalLock(h_global)
    if not locked:
        kernel32.GlobalFree(h_global)
        raise OSError("GlobalLock failed")

    try:
        ctypes.memmove(locked, encoded, size)
    finally:
        kernel32.GlobalUnlock(h_global)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(h_global)
        raise OSError("OpenClipboard failed")

    try:
        if not user32.EmptyClipboard():
            raise OSError("EmptyClipboard failed")
        if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
            raise OSError("SetClipboardData failed")

        # SetClipboardData 成功后，系统接管 h_global，不能再 GlobalFree。
        h_global = None
    finally:
        user32.CloseClipboard()
        if h_global:
            kernel32.GlobalFree(h_global)
```

注意：这段代码需要小心测试。`ctypes` 的返回类型和参数类型在 64 位 Windows 上最好显式设置：

```python
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.restype = ctypes.c_void_p
user32.SetClipboardData.restype = ctypes.c_void_p
```

---

## 8. HTTP/API 层需要检查的点

Windows backend 理想上不应该修改 HTTP API 行为。

需要检查这些调用点：

- `POST /send`
- 网页端“发送文本”
- 网页端“自动上屏”
- 网页端“发送回车”
- 历史记录保存
- 错误消息返回

建议让 HTTP 层收到统一的 `BackendResult`：

```json
{
  "ok": true,
  "backend": "windows",
  "message": "copied to Windows clipboard"
}
```

错误时：

```json
{
  "ok": false,
  "backend": "windows",
  "error": "SendInput failed: sent=0, expected=4"
}
```

---

## 9. 配置项建议

新增/调整环境变量：

```text
NETWORK_INPUT_BACKEND=auto
NETWORK_INPUT_WINDOWS_CLIPBOARD=winapi
NETWORK_INPUT_WINDOWS_PASTE_DELAY_MS=80
```

说明：

- `NETWORK_INPUT_BACKEND=auto`：默认按平台自动选择；
- `NETWORK_INPUT_WINDOWS_CLIPBOARD=winapi|tkinter`：可选，默认 `winapi`；
- `NETWORK_INPUT_WINDOWS_PASTE_DELAY_MS`：写入剪贴板后等待一小段时间再发送粘贴快捷键，避免某些应用还没读到剪贴板。

建议默认 delay：

```text
50ms ~ 100ms
```

实现上：

```python
time.sleep(delay_ms / 1000)
```

---

## 10. 测试计划

### 10.1 单元测试：平台选择

新增 `tests/test_backends.py` 或扩展现有测试。

测试点：

- `NETWORK_INPUT_BACKEND=auto` + `sys.platform == "win32"` 时选择 `WindowsBackend`
- `NETWORK_INPUT_BACKEND=windows` 时选择 `WindowsBackend`
- 非 Windows 强制使用 `windows` 时给出清晰错误
- 未知 backend 名称时报错

建议用 monkeypatch：

```python
def test_auto_selects_windows_on_win32(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    backend = create_backend("auto")
    assert backend.name == "windows"
```

### 10.2 单元测试：SendInput 事件序列

不要在 CI 里真的发送按键。

应把底层 `_send_inputs()` 做成可注入函数，或者 monkeypatch 掉：

```python
def test_windows_paste_ctrl_v_sends_expected_sequence(monkeypatch):
    calls = []

    def fake_send_inputs(inputs):
        calls.append(inputs)

    monkeypatch.setattr(windows_backend, "_send_inputs", fake_send_inputs)

    backend = WindowsBackend()
    backend.paste("ctrl_v")

    assert len(calls) == 1
    # 检查 Ctrl down, V down, V up, Ctrl up
```

### 10.3 单元测试：剪贴板

CI 中不要依赖真实 Windows 剪贴板。

建议拆成两层：

```text
WindowsBackend.set_clipboard()
  -> set_clipboard_text()
     -> _set_clipboard_text_winapi()
```

测试 `WindowsBackend` 调用了 `set_clipboard_text()` 即可。

WinAPI 真实剪贴板测试放到手动测试，或者使用 `pytest.mark.windows_manual`。

### 10.4 集成测试：HTTP API

现有 `test_http_api.py` 应该加入 fake backend：

- 请求 `/send` 成功后，fake backend 收到 text；
- auto_paste 参数正确传到 backend；
- paste_mode 正确传到 backend；
- press_enter 正确传到 backend；
- backend 抛错时，HTTP 返回可读错误。

---

## 11. Windows 手动验收清单

在 Windows 10/11 上测试：

### 11.1 基础启动

```powershell
uv sync
uv run python -m network_input
```

浏览器访问：

```text
http://localhost:18502
http://<局域网IP>:18502
```

验收：

- 页面能打开；
- 终端显示服务监听地址；
- 手机能访问局域网地址；
- 联机申请/允许流程正常。

### 11.2 只写剪贴板

操作：

1. 手机页面输入 `你好 Windows`
2. 不勾选自动上屏
3. 点击发送
4. 在 Windows 上手动 `Ctrl+V`

验收：

- 当前应用能粘贴出 `你好 Windows`
- 中文不乱码
- emoji 不乱码，例如 `测试😀`
- 多行文本换行保留

### 11.3 自动上屏 Ctrl+V

操作：

1. Windows 打开记事本
2. 光标聚焦在文本框
3. 手机页面输入文本
4. 勾选自动上屏
5. 选择 `Ctrl+V`
6. 点击发送

验收：

- 文本自动出现在记事本
- 连续发送 5 次无异常
- 中文、英文、emoji、多行文本都能正常粘贴

### 11.4 自动上屏 Ctrl+Shift+V

操作：

1. Windows Terminal / PowerShell / 其他终端聚焦
2. 选择 `Ctrl+Shift+V`
3. 发送文本

验收：

- 支持 `Ctrl+Shift+V` 的终端能粘贴
- 如果目标程序不支持，应只表现为目标程序不响应，不应导致服务崩溃

### 11.5 发送回车

操作：

1. 打开记事本或终端
2. 点击网页端“发送回车”

验收：

- 当前焦点应用收到 Enter
- 不依赖文本内容

### 11.6 管理员窗口限制

操作：

1. 以管理员权限打开某个程序
2. 普通权限运行 `py-network-input`
3. 尝试自动粘贴

验收：

- 剪贴板写入成功
- 自动上屏可能失败或无效
- 文档中说明这是 Windows 权限隔离导致的限制

---

## 12. README 更新计划

README 需要增加 Windows 说明。

建议新增章节：

```markdown
## Windows 支持

Windows 下无需安装 `wl-clipboard` / `wtype`。

启动：

```powershell
uv sync
uv run python -m network_input
```

默认会自动选择 Windows 后端：

```powershell
$env:NETWORK_INPUT_BACKEND="auto"
```

也可以强制选择：

```powershell
$env:NETWORK_INPUT_BACKEND="windows"
```

支持功能：

- 写入 Windows 剪贴板
- 自动发送 `Ctrl+V`
- 自动发送 `Ctrl+Shift+V`
- 发送回车

注意：

- 自动上屏依赖当前焦点窗口。
- 如果目标应用以管理员权限运行，而本工具不是管理员权限，Windows 可能阻止按键注入。
- 某些安全软件可能拦截模拟输入。
```

---

## 13. pyproject.toml / 依赖策略

当前项目依赖为空，建议首版 Windows backend 继续保持无第三方依赖。

优先：

```text
ctypes
sys
os
time
dataclasses
typing
```

暂不引入：

```text
pyautogui
pynput
pywin32
pyperclip
```

原因：

- 降低安装失败概率；
- 避免 GUI 自动化库的额外依赖；
- 后续打包更容易；
- 现有项目定位是轻量工具。

如果 WinAPI 剪贴板实现成本过高，可以先用 `tkinter`，但 README 要说明极少数精简 Python 发行版可能不包含 Tk。

---

## 14. 实现顺序建议

### Phase 1：最小 Windows 可用

目标：Windows 能写剪贴板 + 自动 Ctrl+V + 回车。

任务：

1. 新增 `WindowsBackend`
2. 实现 Windows 剪贴板写入
3. 实现 `SendInput` 热键
4. 修改 backend 选择逻辑
5. 加单元测试
6. 更新 README

验收：

- Windows 上发送文本到剪贴板成功；
- 勾选自动上屏后可粘贴到记事本；
- 发送回车可用；
- Linux 原有测试不失败。

### Phase 2：结构重构

目标：后端结构清楚，方便未来加 X11/macOS。

任务：

1. 新增 `network_input/backends/`
2. 把 Wayland 逻辑迁移到 `backends/wayland.py`
3. Windows 逻辑放到 `backends/windows.py`
4. `input_backends.py` 作为兼容导出或删除
5. 补充 `NoopBackend` / `ClipboardOnlyBackend`

验收：

- API 层完全不关心平台；
- 所有后端共享相同接口；
- 测试能覆盖平台选择。

### Phase 3：增强体验

目标：提升 Windows 日常可用性。

任务：

1. 启动时打印局域网 IP
2. Windows 防火墙提示说明
3. 自动生成 QR Code，可选
4. 添加托盘图标，可选
5. 支持持久化信任设备，可选
6. 支持历史记录持久化，可选

---

## 15. Codex 实施提示词

可以把下面这段直接给 Codex：

```text
请根据 plan.md 为 py-network-input 增加 Windows backend。

优先目标：
1. 保持现有 Linux Wayland 行为不破坏。
2. 新增 WindowsBackend，支持：
   - 写入 Windows 剪贴板；
   - 发送 Ctrl+V；
   - 发送 Ctrl+Shift+V；
   - 发送 Enter。
3. 优先使用 Python 标准库 ctypes 调用 WinAPI，不引入第三方依赖。
4. 修改 NETWORK_INPUT_BACKEND=auto 的平台选择逻辑：
   - win32 -> WindowsBackend
   - Wayland -> WaylandBackend
   - 否则使用现有 clipboard-only 或报清晰错误
5. 为 backend 选择和 Windows 热键事件序列增加单元测试。
6. 更新 README 的 Windows 使用说明。

实现时请先查看当前 network_input/input_backends.py、service.py、http_api.py、config.py 和 tests/ 目录，不要大规模重写无关代码。
如果必须重构，请保持提交粒度清晰：
- refactor: introduce backend interface
- feat: add Windows backend
- test: cover Windows backend selection and hotkeys
- docs: document Windows usage
```

---

## 16. 推荐提交拆分

### Commit 1

```text
refactor: introduce input backend interface

- Add common backend result and protocol.
- Keep existing Wayland clipboard/wtype behavior.
- Preserve current environment variable behavior.
```

### Commit 2

```text
feat: add Windows input backend

- Implement Windows clipboard write support.
- Implement Ctrl+V, Ctrl+Shift+V, and Enter via SendInput.
- Select Windows backend automatically on win32.
```

### Commit 3

```text
test: cover Windows backend selection and hotkey events

- Add tests for backend auto selection.
- Mock SendInput event dispatch.
- Verify paste mode mapping.
```

### Commit 4

```text
docs: add Windows usage notes

- Document Windows startup.
- Explain auto paste limitations.
- Mention administrator privilege and focus-window constraints.
```

---

## 17. 风险与注意事项

### 17.1 权限隔离

Windows 的输入注入受权限级别影响。普通权限进程不能稳定向管理员权限窗口发送模拟键盘输入。

处理方式：

- 不要尝试绕过；
- README 中说明；
- 错误信息保持友好；
- 剪贴板写入仍应可用。

### 17.2 当前焦点窗口

自动粘贴只会作用于当前焦点窗口。服务无法知道用户真正想粘贴到哪里。

处理方式：

- UI 文案写清楚：“请先把光标放到目标输入框”
- 自动上屏默认关闭，避免误输入。

### 17.3 安全边界

局域网输入工具本质上能向当前机器写剪贴板和模拟键盘，因此必须继续保持安全机制：

- 网页端首次联机确认；
- `/send` 继续要求 Bearer Token；
- 不要默认暴露无认证脚本接口；
- 后续可以考虑持久化信任设备，但不要绕过首次确认。

### 17.4 杀软/安全软件

模拟键盘可能被部分安全软件拦截。

处理方式：

- 不要把失败当作崩溃；
- 返回清晰错误；
- 文档中说明可能受安全软件影响。

---

## 18. 最终验收标准

完成后应满足：

- [ ] Windows 10/11 可以启动服务；
- [ ] 手机能访问 Windows 主机局域网地址；
- [ ] 手机发送文本后 Windows 剪贴板内容正确；
- [ ] 中文、emoji、多行文本正常；
- [ ] `Ctrl+V` 自动上屏可用；
- [ ] `Ctrl+Shift+V` 自动上屏可用；
- [ ] 发送回车可用；
- [ ] Linux Wayland 原有功能不回退；
- [ ] 单元测试通过；
- [ ] README 包含 Windows 使用说明；
- [ ] 没有新增不必要的第三方依赖。
