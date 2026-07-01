from __future__ import annotations

from abc import ABC, abstractmethod
import shutil
import subprocess


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


def create_input_backend(name: str) -> InputBackend:
    if name in {"clipboard", "wl-copy", "wtype"}:
        return ClipboardBackend()
    raise ValueError(f"不支持的输入后端: {name}")
