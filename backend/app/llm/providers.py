from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    name: str
    base_url: str | None
    model_examples: tuple[str, ...]
    docs_url: str
    description: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["model_examples"] = list(self.model_examples)
        return data


PROVIDER_PRESETS = {
    "openai": ProviderPreset(
        id="openai",
        name="OpenAI",
        base_url=None,
        model_examples=(),
        docs_url="https://developers.openai.com/api/docs/",
        description="OpenAI 官方 API",
    ),
    "deepseek": ProviderPreset(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com",
        model_examples=("deepseek-v4-flash", "deepseek-v4-pro"),
        docs_url="https://api-docs.deepseek.com/zh-cn/",
        description="DeepSeek OpenAI 兼容接口",
    ),
    "zhipu": ProviderPreset(
        id="zhipu",
        name="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model_examples=("glm-5.2",),
        docs_url="https://docs.bigmodel.cn/cn/guide/develop/openai/introduction",
        description="智谱开放平台 OpenAI 兼容接口",
    ),
    "kimi": ProviderPreset(
        id="kimi",
        name="Kimi",
        base_url="https://api.moonshot.cn/v1",
        model_examples=("kimi-k3", "kimi-k2.6"),
        docs_url="https://platform.kimi.com/docs/overview",
        description="Moonshot Kimi OpenAI 兼容接口",
    ),
    "minimax": ProviderPreset(
        id="minimax",
        name="MiniMax",
        base_url="https://api.minimaxi.com/v1",
        model_examples=("MiniMax-M2.7", "MiniMax-M2.7-highspeed"),
        docs_url="https://platform.minimaxi.com/docs/api-reference/text-openai-api",
        description="MiniMax 国内开放平台 OpenAI 兼容接口",
    ),
    "qwen": ProviderPreset(
        id="qwen",
        name="通义千问",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_examples=("qwen-plus",),
        docs_url="https://help.aliyun.com/en/model-studio/base-url",
        description="阿里云百炼中国内地 OpenAI 兼容接口",
    ),
    "doubao": ProviderPreset(
        id="doubao",
        name="豆包",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        model_examples=("doubao-seed-2-0-lite-260215",),
        docs_url="https://www.volcengine.com/docs/82379/1795150",
        description="火山方舟 OpenAI 兼容接口",
    ),
    "custom": ProviderPreset(
        id="custom",
        name="自定义兼容接口",
        base_url=None,
        model_examples=(),
        docs_url="",
        description="任何兼容 OpenAI Chat Completions 的服务",
    ),
}


def get_provider(provider_id: str) -> ProviderPreset:
    try:
        return PROVIDER_PRESETS[provider_id]
    except KeyError as exc:
        raise ValueError(f"不支持的 AI 供应商：{provider_id}") from exc


def resolve_base_url(provider_id: str, custom_value: str | None) -> str | None:
    preset = get_provider(provider_id)
    resolved = custom_value or preset.base_url
    if provider_id == "custom" and not resolved:
        raise ValueError("自定义供应商必须填写 Base URL")
    return resolved
