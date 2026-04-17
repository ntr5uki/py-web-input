from __future__ import annotations

from abc import ABC, abstractmethod
import shutil
import subprocess

from .text import normalize_input_text


class InputInjectionError(RuntimeError):
    """Raised when text injection fails."""


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


class WtypeBackend(InputBackend):
    def is_available(self) -> bool:
        return shutil.which("wtype") is not None

    def describe(self) -> str:
        return "Wayland `wtype` 直接输入后端"

    def inject(self, text: str) -> None:
        if not self.is_available():
            raise InputInjectionError("未找到 `wtype`，请先在系统中安装该命令。")

        completed = subprocess.run(
            build_wtype_command(text),
            capture_output=True,
            text=True,
            check=False,
        )

        release_result = release_wtype_modifiers()
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or "wtype 执行失败"
            if release_result.returncode != 0 and release_result.stderr.strip():
                stderr = f"{stderr}；修饰键释放失败：{release_result.stderr.strip()}"
            raise InputInjectionError(stderr)


def build_wtype_command(text: str) -> list[str]:
    return ["wtype", normalize_input_text(text)]


def build_wtype_release_command() -> list[str]:
    return [
        "wtype",
        "-m",
        "shift",
        "-m",
        "capslock",
        "-m",
        "ctrl",
        "-m",
        "logo",
        "-m",
        "altgr",
    ]


def release_wtype_modifiers() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_wtype_release_command(),
        capture_output=True,
        text=True,
        check=False,
    )


def create_input_backend(name: str) -> InputBackend:
    if name == "wtype":
        return WtypeBackend()
    raise ValueError(f"不支持的输入后端: {name}")
