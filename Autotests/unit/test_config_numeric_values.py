import config


def test_numeric_command_line_values_survive_as_numbers():
    config.init_config(["maxNewInputLoops=8", "model=moonshotai.kimi-k2.5"])

    value = config.config_get_by_key("maxNewInputLoops")
    assert value == 8
    assert isinstance(value, int)
    assert config.config_get_by_key("model") == "moonshotai.kimi-k2.5"
