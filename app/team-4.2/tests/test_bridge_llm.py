from rag.bridge.llm import OPENROUTER_URL, concept_tag_llm
from rag.config import Settings


def test_default_is_haiku_via_openrouter_without_temperature():
    llm = concept_tag_llm(Settings(openrouter_api_key="k"))
    assert llm.model_id == "anthropic/claude-haiku-5.5"
    assert llm.temperature is None                      # Claude 5.x từ chối temperature khác mặc định
    assert (llm._base_url, llm._api_key) == (OPENROUTER_URL, "k")


def test_app_means_use_app_llm():
    assert concept_tag_llm(Settings(openrouter_api_key="k", concept_tag_model="app")) is None


def test_no_openrouter_key_falls_back_to_app_llm():
    assert concept_tag_llm(Settings(openrouter_api_key=None)) is None


def test_env_name():
    s = Settings.from_env({"CONCEPT_TAG_MODEL": "anthropic/claude-sonnet-5.5", "OPENROUTER_API_KEY": "k"})
    assert concept_tag_llm(s).model_id == "anthropic/claude-sonnet-5.5"


def test_contract_agent_model_defaults_to_app_llm():
    from rag.bridge.llm import contract_agent_llm
    assert contract_agent_llm(Settings(openrouter_api_key="k")) is None
    s = Settings.from_env({"CONTRACT_AGENT_MODEL": "anthropic/claude-sonnet-5.5", "OPENROUTER_API_KEY": "k"})
    assert contract_agent_llm(s).model_id == "anthropic/claude-sonnet-5.5"
    assert contract_agent_llm(Settings(contract_agent_model="anthropic/claude-sonnet-5.5")) is None   # thiếu key
