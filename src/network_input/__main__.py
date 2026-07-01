from __future__ import annotations

import sys
import threading

from .config import AppConfig
from .runtime import AppRuntime


def run_command_console(runtime: AppRuntime) -> None:
    while True:
        try:
            raw = input("> ").strip()
        except EOFError:
            return
        if not raw:
            continue
        if raw in {"help", "h", "?"}:
            print("命令：list | allow <id> | deny <id>")
            continue
        if raw in {"list", "ls"}:
            pending = runtime.pairing.list_pending_requests()
            if not pending:
                print("当前没有待确认请求。")
                continue
            for item in pending:
                print(
                    f"[{item.request_id}] {item.remote_addr} client={item.client_id} "
                    f"created={item.created_at.isoformat()}"
                )
            continue
        command, _, arg = raw.partition(" ")
        if command == "allow" and arg.isdigit():
            try:
                item = runtime.pairing.approve_request(int(arg))
            except KeyError as exc:
                print(str(exc))
            else:
                print(f"已允许请求 {item.request_id}，client={item.client_id}")
            continue
        if command == "deny" and arg.isdigit():
            try:
                item = runtime.pairing.reject_request(int(arg))
            except KeyError as exc:
                print(str(exc))
            else:
                print(f"已拒绝请求 {item.request_id}，client={item.client_id}")
            continue
        print("未知命令，输入 help 查看可用命令。")


def main() -> None:
    runtime = AppRuntime(AppConfig.from_env()).start()
    urls = runtime.web_urls()
    print("局域网文字投送服务已启动")
    print(f"本地地址: {urls[0]}")
    if len(urls) > 1:
        print(f"局域网地址: {urls[1]}")
    if sys.stdin.isatty():
        print("配对命令：list | allow <id> | deny <id> | help")
        threading.Thread(target=run_command_console, args=(runtime,), daemon=True).start()
    try:
        runtime.wait_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
