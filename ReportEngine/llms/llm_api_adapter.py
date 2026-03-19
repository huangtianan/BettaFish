from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional

from nextagent.llm import LLMApi


class LLMApiAdapter:
    """
    把 nextagent 的 LLMApi 适配成 ReportEngine 期望的 llm_client 接口。

    目标方法：
    - invoke(system_prompt, user_prompt, **kwargs) -> str
    - stream_invoke(system_prompt, user_prompt, **kwargs) -> Generator[str, None, None]
    - stream_invoke_to_string(system_prompt, user_prompt, **kwargs) -> str
    - get_model_info() -> dict
    """

    def __init__(self, llm_api: LLMApi):
        self.llm_api = llm_api

    def _get_default_model(self) -> str:
        cfg = getattr(self.llm_api, "config", None)
        model = getattr(cfg, "model", None)
        return str(model or "")

    def get_model_info(self) -> Dict[str, Any]:
        cfg = getattr(self.llm_api, "config", None)
        api_type = getattr(cfg, "api_type", None) or "unknown"
        api_base = getattr(cfg, "api_base", None) or None
        model = getattr(cfg, "model", None) or None
        return {
            "provider": api_type,
            "model": model,
            "api_base": api_base or "default",
        }

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # ReportEngine 的 invoke 是非流式语义，这里强制 stream=False。
        msg = self.llm_api.chat_completion(
            messages=messages,
            model=self._get_default_model(),
            stream=False,
            temperature=kwargs.get("temperature", None),
            max_tokens=kwargs.get("max_tokens", None),
            top_p=kwargs.get("top_p", None),
            stop=kwargs.get("stop", None),
            **{
                # 一些 completion service 可能支持 presence/frequency_penalty 等参数
                k: v
                for k, v in kwargs.items()
                if k in {"presence_penalty", "frequency_penalty"} and v is not None
            },
        )

        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
        return (content or "").strip()

    def stream_invoke(
        self, system_prompt: str, user_prompt: str, **kwargs
    ) -> Generator[str, None, None]:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 禁用 smoother：ReportEngine 自己负责“把 delta 写入 raw 文件”。
        stream = self.llm_api.chat_completion_stream(
            messages=messages,
            model=self._get_default_model(),
            stream=True,
            temperature=kwargs.get("temperature", None),
            max_tokens=kwargs.get("max_tokens", None),
            top_p=kwargs.get("top_p", None),
            stop=kwargs.get("stop", None),
            use_smoother=False,
        )

        for msg_chunk in stream:
            if isinstance(msg_chunk, dict):
                delta = msg_chunk.get("content") or ""
            else:
                delta = getattr(msg_chunk, "content", "") or ""
            if delta:
                yield delta

    def stream_invoke_to_string(
        self, system_prompt: str, user_prompt: str, **kwargs
    ) -> str:
        chunks: List[str] = []
        for delta in self.stream_invoke(system_prompt, user_prompt, **kwargs):
            chunks.append(delta)
        return "".join(chunks)

