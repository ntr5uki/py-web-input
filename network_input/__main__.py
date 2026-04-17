from __future__ import annotations

from .config import AppConfig
from .runtime import AppRuntime


def main() -> None:
    runtime = AppRuntime(AppConfig.from_env()).start()
    urls = runtime.web_urls()
    print("局域网文字投送服务已启动")
    print(f"本地地址: {urls[0]}")
    if len(urls) > 1:
        print(f"局域网地址: {urls[1]}")
    try:
        runtime.wait_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
