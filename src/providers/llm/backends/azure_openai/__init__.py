from providers.exceptions import LLMError
from providers.models import AzureGenerateContentConfig, ModelBasicInfo

from .base import AzureOpenAILLMBase
from .models import AzureOpenAIGPT4, AzureOpenAIGPT5

__all__ = [
    "AzureOpenAILLMBase",
    "AzureOpenAIGPT4",
    "AzureOpenAIGPT5",
    "create_azure_openai_llm",
]


def create_azure_openai_llm(
    model_info: ModelBasicInfo,
    config: AzureGenerateContentConfig | None = None,
) -> AzureOpenAILLMBase:
    if model_info.model_name.startswith("gpt-5"):
        return AzureOpenAIGPT5(model_info, config)
    if model_info.model_name.startswith("gpt-4"):
        return AzureOpenAIGPT4(model_info, config)
    raise LLMError(
        "Unsupported model",
        f"Model {model_info.model_name} is not supported. Use GPT-4 or GPT-5.",
    )
