def test_think_tool_name_is_stable():
    from app.tools.think_tool import think_tool

    assert think_tool.name == "think_tool"


def test_think_tool_description_mentions_reflection_and_gap():
    from app.tools.think_tool import think_tool

    desc = (think_tool.description or "").lower()
    assert "reflect" in desc
    assert "gap" in desc


def test_think_tool_echoes_reflection():
    from app.tools.think_tool import think_tool

    result = think_tool.invoke({"reflection": "need primary source on X"})

    assert isinstance(result, str)
    assert "need primary source on X" in result


def test_think_tool_has_single_reflection_arg():
    """Model should see exactly one string arg called `reflection`."""
    from app.tools.think_tool import think_tool

    schema = think_tool.args_schema.model_json_schema()
    assert set(schema["properties"]) == {"reflection"}
    assert schema["properties"]["reflection"]["type"] == "string"
