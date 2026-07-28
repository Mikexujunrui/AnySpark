from core.config import AppConfig, config


def test_config_loads():
    assert config is not None
    assert isinstance(config, AppConfig)


def test_config_defaults():
    # max_rounds=0 means unlimited; soft_round_limit=0 means no progressive warnings.
    assert config.agent.max_rounds == 0
    assert config.agent.soft_round_limit == 0
    assert config.agent.max_workers == 8
    assert config.agent.default_temperature == 0.3
    assert config.storage.max_chapter_chars == 256000
    assert config.server.port in (8191, 8123)  # default 8191, may be overridden by env


def test_config_llm():
    assert config.llm.base_url
    assert config.llm.model_pro
    assert config.llm.model_flash == "deepseek-v4-flash"
    assert config.llm.mode in ("quality", "split", "flash")
