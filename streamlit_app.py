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


runtime = get_runtime()

st.title("局域网文字投送")
st.caption("收到的文字会通过 Wayland `wtype` 直接输入到当前焦点位置。")

with st.sidebar:
    st.subheader("运行状态")
    st.write(f"后端类型：`{runtime.config.input_backend}`")
    st.write(f"HTTP API：`{'已开启' if runtime.api else '已关闭'}`")
    if runtime.api:
        st.write(f"接口端口：`{runtime.api.port}`")
    st.write(f"鉴权：`{'已开启' if runtime.config.api_token else '未开启'}`")
    if runtime.service.backend_ready():
        st.success("已检测到 `wtype`。")
    else:
        st.error("未检测到 `wtype`，发送会失败。")

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
        st.info("HTTP API 已关闭；仍可通过本页面发送并自动上屏。")

left, right = st.columns([3, 2])

with left:
    with st.form("send-text-form", clear_on_submit=True):
        text = st.text_area("文本内容", height=140, placeholder="输入要投送到当前焦点位置的文字")
        submitted = st.form_submit_button("发送")

    if submitted:
        try:
            record = runtime.service.submit(text=text, source="streamlit")
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success(f"已加入发送队列：{record.message_id}")

with right:
    @st.fragment(run_every="2s")
    def render_live_status() -> None:
        st.subheader("最近状态")
        latest_history = runtime.service.list_history()
        latest = latest_history[0] if latest_history else None
        if latest:
            st.write(f"最新消息：`{latest.message_id}`")
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
                    f"**{item.message_id}** · {render_status_badge(item)} · `{item.source}`",
                    item.text.replace("\n", "  \n"),
                ]
            )
        )
        if item.error:
            st.caption(f"错误：{item.error}")
        st.divider()


render_history()
