"""AI 客户端 — 多 Provider 统一调用层"""

from openai import OpenAI, APIConnectionError, AuthenticationError, RateLimitError
from config import MODEL_CONFIGS
from ai.doubao import doubao_call, doubao_stream


def get_ai_client(model_name: str) -> tuple[OpenAI | None, dict | None, str | None]:
    """返回 (client, config, error_msg)"""
    cfg = MODEL_CONFIGS.get(model_name)
    if not cfg:
        return None, None, "未知模型配置"
    if not cfg["api_key"]:
        return None, cfg, f"「{model_name}」的 API Key 尚未配置"
    try:
        extra_kwargs = {}
        if cfg.get("provider") == "openrouter":
            extra_kwargs["default_headers"] = {
                "HTTP-Referer": "https://a-stock-research-assistant.streamlit.app",
                "X-Title": "A-Stock Research Assistant",
            }
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], **extra_kwargs)
        return client, cfg, None
    except Exception as e:
        return None, cfg, str(e)


def _build_messages(prompt: str, system: str = "") -> list[dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _build_extra(cfg: dict) -> dict:
    """根据 provider 构建联网搜索等额外参数"""
    extra: dict = {}
    if not cfg.get("supports_search"):
        return extra
    provider = cfg.get("provider")
    if provider == "qwen":
        extra["extra_body"] = {"enable_search": True}
    elif provider == "zhipu":
        extra["tools"] = [{"type": "web_search", "web_search": {"enable": True}}]
    elif provider == "openrouter":
        extra["extra_body"] = {"plugins": [{"id": "web", "max_results": 5}]}
    return extra


def call_ai(client: OpenAI, cfg: dict, prompt: str,
            system: str = "", max_tokens: int = 8000) -> tuple[str, str | None]:
    """
    调用 AI 模型，返回 (text, error_msg)。
    豆包走 responses API，其他走 chat.completions。
    """
    messages = _build_messages(prompt, system)

    # 豆包专属路径
    if cfg.get("provider") == "doubao" and cfg.get("supports_search"):
        return doubao_call(cfg, messages, max_tokens)

    extra = _build_extra(cfg)
    try:
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            max_tokens=max_tokens,
            **extra,
        )
        text = resp.choices[0].message.content or ""
        return text, None

    except AuthenticationError as e:
        return "", f"API Key 认证失败：{str(e)[:200]}"
    except RateLimitError:
        return "", "调用频率或额度超限，请稍后重试或切换其他模型"
    except APIConnectionError as e:
        return "", f"网络连接失败：{e}"
    except Exception as e:
        err = str(e)
        if "invalid_api_key" in err.lower() or "401" in err:
            return "", f"API Key 无效或模型不可用：{err[:200]}"
        if "quota" in err.lower() or "insufficient" in err.lower():
            return "", "账户余额不足，请充值或切换模型"
        if "model_not_found" in err.lower() or "does not exist" in err.lower():
            return "", f"模型不存在（{cfg['model']}），请联系开发者更新模型名称"
        return "", f"AI 调用异常：{err[:120]}"


def call_ai_stream(client: OpenAI, cfg: dict, prompt: str,
                   system: str = "", max_tokens: int = 8000):
    """
    流式调用 AI 模型，yield 文本片段。
    豆包走 responses API 流式。
    """
    messages = _build_messages(prompt, system)

    # 豆包专属路径
    if cfg.get("provider") == "doubao" and cfg.get("supports_search"):
        yield from doubao_stream(cfg, messages, max_tokens)
        return

    extra = _build_extra(cfg)
    try:
        stream = client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            **extra,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except AuthenticationError as e:
        yield f"\n\n⚠️ API Key 认证失败：{str(e)[:200]}"
    except RateLimitError:
        yield "\n\n⚠️ 调用频率或额度超限，请稍后重试或切换其他模型"
    except APIConnectionError as e:
        yield f"\n\n⚠️ 网络连接失败：{e}"
    except Exception as e:
        yield f"\n\n⚠️ AI 调用异常：{str(e)[:120]}"
