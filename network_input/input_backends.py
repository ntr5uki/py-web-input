from __future__ import annotations

from abc import ABC, abstractmethod
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import shutil
import subprocess
import sys
import time
from typing import Iterable


class InputInjectionError(RuntimeError):
    """Raised when text delivery fails."""


class InputBackend(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def inject(self, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def press_shortcut(self, shortcut: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def press_key(self, key: str) -> None:
        raise NotImplementedError


class ClipboardBackend(InputBackend):
    def is_available(self) -> bool:
        return shutil.which("wl-copy") is not None

    def describe(self) -> str:
        return "Wayland `wl-copy` 剪贴板后端"

    def inject(self, text: str) -> None:
        if not self.is_available():
            raise InputInjectionError("未找到 `wl-copy`，请先安装 `wl-clipboard`。")

        try:
            completed = subprocess.run(
                build_wl_copy_command(),
                input=text,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=3,
            )
        except subprocess.TimeoutExpired as exc:
            raise InputInjectionError("wl-copy 写入剪贴板超时") from exc
        if completed.returncode != 0:
            raise InputInjectionError("wl-copy 写入剪贴板失败")

    def press_shortcut(self, shortcut: str) -> None:
        if shutil.which("wtype") is None:
            raise InputInjectionError("未找到 `wtype`，无法自动上屏。")
        self._run_wtype_command(build_wtype_shortcut_command(shortcut), f"发送快捷键失败：{shortcut}")

    def press_key(self, key: str) -> None:
        if shutil.which("wtype") is None:
            raise InputInjectionError("未找到 `wtype`，无法发送按键。")
        self._run_wtype_command(build_wtype_key_command(key), f"发送按键失败：{key}")

    def _run_wtype_command(self, command: list[str], error_message: str) -> None:
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=3,
            )
        except subprocess.TimeoutExpired as exc:
            raise InputInjectionError(f"{error_message}（超时）") from exc
        if completed.returncode != 0:
            raise InputInjectionError(error_message)


def build_wl_copy_command() -> list[str]:
    return ["wl-copy"]


def build_wtype_shortcut_command(shortcut: str) -> list[str]:
    tokens = [item.strip().lower() for item in shortcut.split("+") if item.strip()]
    if not tokens:
        raise ValueError("快捷键不能为空。")
    if len(tokens) == 1:
        return build_wtype_key_command(tokens[0])

    modifiers = [normalize_modifier_name(item) for item in tokens[:-1]]
    key = normalize_key_name(tokens[-1])
    command = ["wtype"]
    for modifier in modifiers:
        command.extend(["-M", modifier])
    command.extend(["-k", key])
    for modifier in reversed(modifiers):
        command.extend(["-m", modifier])
    return command


def build_wtype_key_command(key: str) -> list[str]:
    return ["wtype", "-k", normalize_key_name(key)]


def normalize_modifier_name(name: str) -> str:
    aliases = {
        "control": "ctrl",
        "ctrl": "ctrl",
        "shift": "shift",
    }
    normalized = aliases.get(name)
    if normalized is None:
        raise ValueError(f"不支持的修饰键: {name}")
    return normalized


def normalize_key_name(name: str) -> str:
    aliases = {
        "enter": "Return",
        "return": "Return",
        "v": "v",
    }
    return aliases.get(name.lower(), name)


VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_RETURN = 0x0D
VK_V = 0x56

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


@dataclass(frozen=True, slots=True)
class WindowsKeyEvent:
    vk: int
    key_up: bool = False


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


EXPECTED_INPUT_SIZE = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


class WindowsBackend(InputBackend):
    def __init__(self, paste_delay_ms: int = 80) -> None:
        self._paste_delay_ms = max(0, paste_delay_ms)

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def describe(self) -> str:
        return "Windows WinAPI 剪贴板和 SendInput 后端"

    def inject(self, text: str) -> None:
        _set_windows_clipboard_text(text)

    def press_shortcut(self, shortcut: str) -> None:
        if self._paste_delay_ms:
            time.sleep(self._paste_delay_ms / 1000)
        events = build_windows_shortcut_events(shortcut)
        _send_windows_key_events(events)

    def press_key(self, key: str) -> None:
        events = build_windows_key_events(key)
        _send_windows_key_events(events)


def build_windows_shortcut_events(shortcut: str) -> list[WindowsKeyEvent]:
    tokens = [item.strip().lower() for item in shortcut.split("+") if item.strip()]
    if not tokens:
        raise ValueError("快捷键不能为空。")
    if len(tokens) == 1:
        return build_windows_key_events(tokens[0])

    modifiers = [_windows_modifier_vk(item) for item in tokens[:-1]]
    key = _windows_key_vk(tokens[-1])
    return build_windows_hotkey_events([*modifiers, key])


def build_windows_key_events(key: str) -> list[WindowsKeyEvent]:
    vk = _windows_key_vk(key)
    return [WindowsKeyEvent(vk), WindowsKeyEvent(vk, key_up=True)]


def build_windows_hotkey_events(keys: Iterable[int]) -> list[WindowsKeyEvent]:
    keys = list(keys)
    if not keys:
        raise ValueError("快捷键不能为空。")
    return [
        *[WindowsKeyEvent(key) for key in keys],
        *[WindowsKeyEvent(key, key_up=True) for key in reversed(keys)],
    ]


def _windows_modifier_vk(name: str) -> int:
    aliases = {
        "control": VK_CONTROL,
        "ctrl": VK_CONTROL,
        "shift": VK_SHIFT,
    }
    vk = aliases.get(name)
    if vk is None:
        raise ValueError(f"不支持的 Windows 修饰键: {name}")
    return vk


def _windows_key_vk(name: str) -> int:
    aliases = {
        "enter": VK_RETURN,
        "return": VK_RETURN,
        "v": VK_V,
    }
    vk = aliases.get(name.lower())
    if vk is None:
        raise ValueError(f"不支持的 Windows 按键: {name}")
    return vk


def _send_windows_key_events(events: list[WindowsKeyEvent]) -> None:
    if sys.platform != "win32":
        raise InputInjectionError("Windows SendInput 后端只能在 Windows 上使用。")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT

    inputs = (_windows_input_from_event(event) for event in events)
    input_array = (INPUT * len(events))(*inputs)
    sent = user32.SendInput(len(events), input_array, ctypes.sizeof(INPUT))
    if sent != len(events):
        last_error = ctypes.get_last_error()
        raise InputInjectionError(
            f"SendInput 发送失败：sent={sent}, expected={len(events)}, last_error={last_error}"
        )


def _windows_input_from_event(event: WindowsKeyEvent) -> INPUT:
    flags = KEYEVENTF_KEYUP if event.key_up else 0
    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=event.vk,
            wScan=0,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )


def _set_windows_clipboard_text(text: str) -> None:
    if sys.platform != "win32":
        raise InputInjectionError("Windows 剪贴板后端只能在 Windows 上使用。")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = ()
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = ()
    user32.CloseClipboard.restype = wintypes.BOOL

    encoded = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not handle:
        raise InputInjectionError("Windows 剪贴板内存分配失败。")

    locked = kernel32.GlobalLock(handle)
    if not locked:
        kernel32.GlobalFree(handle)
        raise InputInjectionError("Windows 剪贴板内存锁定失败。")

    try:
        ctypes.memmove(locked, encoded, len(encoded))
    finally:
        kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        kernel32.GlobalFree(handle)
        raise InputInjectionError("打开 Windows 剪贴板失败。")

    try:
        if not user32.EmptyClipboard():
            raise InputInjectionError("清空 Windows 剪贴板失败。")
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise InputInjectionError("写入 Windows 剪贴板失败。")
        handle = None
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def _windows_paste_delay_from_env() -> int:
    raw = os.getenv("NETWORK_INPUT_WINDOWS_PASTE_DELAY_MS", "80").strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError("NETWORK_INPUT_WINDOWS_PASTE_DELAY_MS 必须是整数毫秒。") from exc


def create_input_backend(name: str, *, windows_paste_delay_ms: int | None = None) -> InputBackend:
    normalized = name.strip().lower()
    if normalized == "auto":
        if sys.platform == "win32":
            delay_ms = _windows_paste_delay_from_env() if windows_paste_delay_ms is None else windows_paste_delay_ms
            return WindowsBackend(delay_ms)
        return ClipboardBackend()
    if normalized == "windows":
        if sys.platform != "win32":
            raise ValueError("Windows 输入后端只能在 Windows 上使用。")
        delay_ms = _windows_paste_delay_from_env() if windows_paste_delay_ms is None else windows_paste_delay_ms
        return WindowsBackend(delay_ms)
    if normalized in {"clipboard", "wl-copy", "wtype"}:
        return ClipboardBackend()
    raise ValueError(f"不支持的输入后端: {name}")
