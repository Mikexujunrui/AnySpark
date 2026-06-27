from core.config import AppConfig, config


def test_config_loads():
    assert config is not None
    assert isinstance(config, AppConfig)


def test_config_defaults():
    # max_rounds is the hard safety cap; soft_round_limit is the nudge threshold.
    assert config.agent.max_rounds == 200
    assert config.agent.soft_round_limit == 30
    assert config.agent.max_workers == 8
    assert config.agent.default_temperature == 0.3
    assert config.storage.max_chapter_chars == 256000
    assert config.server.port in (8191, 8123)  # default 8191, may be overridden by env


def test_config_llm():
    assert config.llm.base_url
    assert config.llm.model_pro
    assert config.llm.model_flash == "deepseek-v4-flash"
    assert config.llm.mode in ("quality", "split", "flash")


def test_config_neo4j():
    assert config.neo4j.uri.startswith("bolt://")
    assert config.neo4j.user
    assert config.neo4j.password
