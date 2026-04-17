from __future__ import annotations

import json

import streamlit as st

from network_input import AppConfig, AppRuntime
from network_input.models import MessageRecord, MessageStatus


st.set_page_config(page_title="局域网文字投送", page_icon="⌨️", layout="wide")


@st.cache_resource
def get_runtime() -> AppRuntime:
    return AppRuntime(AppConfig.from_env()).start()


def render_status_badge(record: MessageRecord) -> str:
    if record.status == MessageStatus.SUCCESS:
        return "✅ 成功"
    if record.status == MessageStatus.FAILED:
        return "❌ 失败"
    if record.status == MessageStatus.PROCESSING:
        return "⏳ 处理中"
    return "🕒 排队中"


def render_action_label(record: MessageRecord) -> str:
    if record.action == "copy_and_paste":
        return f"复制并自动上屏（{record.shortcut}）"
    if record.action == "press_key":
        return "发送回车"
    return "复制到剪贴板"


runtime = get_runtime()
latest_history = runtime.service.list_history()
latest_success = next((item for item in latest_history if item.status == MessageStatus.SUCCESS), None)

if st.session_state.get("_clear_send_text"):
    st.session_state["send_text"] = ""
    st.session_state["_clear_send_text"] = False

st.title("局域网文字投送")
st.caption("收到的文字会通过 Wayland `wl-copy` 写入剪贴板，请在目标位置手动粘贴。")

if latest_success:
    if latest_success.action == "press_key":
        st.success("已发送回车。")
    elif latest_success.action == "copy_and_paste":
        st.success("剪贴板已更新，并已触发自动上屏。")
    else:
        st.success("剪贴板已更新，请立刻切到目标窗口手动粘贴。")
    with st.container(border=True):
        st.markdown(f"**最近一次操作** · `{latest_success.message_id}` · {render_action_label(latest_success)}")
        if latest_success.action != "press_key":
            st.code(latest_success.text, language=None, wrap_lines=True)
else:
    st.info("发送成功后，这里会显示明显的复制/上屏提醒。")

with st.sidebar:
    st.subheader("运行状态")
    st.write(f"后端类型：`{runtime.config.input_backend}`")
    st.write(f"HTTP API：`{'已开启' if runtime.api else '已关闭'}`")
    if runtime.api:
        st.write(f"接口端口：`{runtime.api.port}`")
    st.write(f"鉴权：`{'已开启' if runtime.config.api_token else '未开启'}`")
    if runtime.service.backend_ready():
        st.success("已检测到 `wl-copy`。勾选自动上屏或发送回车时还需要 `wtype`。")
    else:
        st.error("未检测到 `wl-copy`，发送会失败。")

    if runtime.api:
        st.subheader("接口地址")
        for url in runtime.api_urls():
            st.code(url, language=None)

        example_payload = {"text": "你好，来自局域网设备", "source": "curl"}
        curl_parts = ["curl", "-X", "POST"]
        if runtime.config.api_token:
            curl_parts.extend(["-H", f"'Authorization: Bearer {runtime.config.api_token}'"])
        curl_parts.extend(
            [
                "-H",
                "'Content-Type: application/json'",
                "-d",
                f"'{json.dumps(example_payload, ensure_ascii=False)}'",
                f"http://127.0.0.1:{runtime.api.port}/send",
            ]
        )
        st.subheader("调用示例")
        st.code(" ".join(curl_parts), language="bash")
    else:
        st.info("HTTP API 已关闭；仍可通过本页面发送到剪贴板。")

left, right = st.columns([3, 2])

with left:
    text = st.text_area(
        "文本内容",
        key="send_text",
        height=140,
        placeholder="输入要投送到当前焦点位置的文字",
    )
    auto_paste = st.checkbox("自动上屏", key="auto_paste")
    paste_shortcut_label = st.radio(
        "粘贴快捷键",
        ["Ctrl+V", "Ctrl+Shift+V"],
        key="paste_shortcut_label",
        horizontal=True,
        disabled=not auto_paste,
    )
    submitted = st.button("发送文本", use_container_width=True)

    if submitted:
        try:
            if auto_paste:
                shortcut = "ctrl+shift+v" if paste_shortcut_label == "Ctrl+Shift+V" else "ctrl+v"
                record = runtime.service.submit_with_auto_paste(text=text, source="streamlit", shortcut=shortcut)
            else:
                record = runtime.service.submit(text=text, source="streamlit")
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["_clear_send_text"] = True
            if record.action == "copy_and_paste":
                st.success(f"已加入自动上屏队列：{record.message_id}。将尝试发送 `{record.shortcut}`。")
            else:
                st.success(f"已加入剪贴板队列：{record.message_id}。剪贴板更新后请立刻手动粘贴。")
            st.rerun()

    if st.button("发送回车", use_container_width=True):
        record = runtime.service.submit_enter(source="streamlit")
        st.success(f"已加入回车队列：{record.message_id}。")

with right:
    @st.fragment(run_every="2s")
    def render_live_status() -> None:
        st.subheader("最近状态")
        latest_history = runtime.service.list_history()
        latest = latest_history[0] if latest_history else None
        if latest:
            st.write(f"最新消息：`{latest.message_id}`")
            st.write(f"动作：`{render_action_label(latest)}`")
            st.write(f"状态：{render_status_badge(latest)}")
            if latest.error:
                st.error(latest.error)
        else:
            st.info("还没有消息。")
        st.write(f"当前排队数量：`{runtime.service.pending_count()}`")

    render_live_status()


@st.fragment(run_every="2s")
def render_history() -> None:
    st.subheader("最近消息")
    current_history = runtime.service.list_history()
    if not current_history:
        st.info("等待第一条消息。")
        return

    for item in current_history:
        st.markdown(
            "\n".join(
                [
                    f"**{item.message_id}** · {render_status_badge(item)} · `{item.source}` · {render_action_label(item)}",
                    item.text.replace("\n", "  \n") if item.action != "press_key" else "（无文本内容）",
                ]
            )
        )
        if item.error:
            st.caption(f"错误：{item.error}")
        st.divider()


render_history()
