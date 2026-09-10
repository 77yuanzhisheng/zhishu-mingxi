import asyncio

from backend.kb.router import get_knowledge_graph, get_node_textbook_mapping


def test_knowledge_graph_exposes_chapters_dependencies_and_stats():
    graph = asyncio.run(get_knowledge_graph())

    modules = graph["modules"]
    dependencies = graph["dependencies"]
    stats = graph["stats"]
    module_ids = {module["node_id"] for module in modules}

    assert stats["module_count"] == len(modules)
    assert stats["chapter_count"] == sum(len(module["children"]) for module in modules)
    assert stats["knowledge_point_count"] == sum(
        len(chapter["items"])
        for module in modules
        for chapter in module["children"]
    )
    assert stats["dependency_count"] == len(dependencies)
    assert dependencies
    assert all(edge["source"] in module_ids for edge in dependencies)
    assert all(edge["target"] in module_ids for edge in dependencies)

    for module_index, module in enumerate(modules, 1):
        assert module["chapter"] == f"第{module_index}章"
        assert module["chapter_count"] == len(module["children"])
        for chapter_index, chapter in enumerate(module["children"], 1):
            assert chapter["type"] == "chapter"
            assert chapter["chapter"] == f"{module_index}.{chapter_index}"
            assert chapter["chapter_title"].startswith(chapter["chapter"])
            assert chapter["parent_node_id"] == module["node_id"]
            assert chapter["item_count"] == len(chapter["items"])
            for item in chapter["items"]:
                assert item["chapter"] == chapter["chapter"]
                assert item["parent_node_id"] == chapter["node_id"]
                assert item["name"]


def test_node_textbook_mapping_supports_parent_nodes_with_multiple_candidates():
    mapping = asyncio.run(get_node_textbook_mapping("rel_02"))

    assert mapping["found"] is True
    assert mapping["node_id"] == "rel_02"
    assert mapping["kpId"] == "K020401"
    assert mapping["chapterId"] == "C02"
    assert [candidate["kpId"] for candidate in mapping["candidates"]] == [
        "K020401",
        "K020402",
        "K020403",
    ]
    assert {candidate["section"] for candidate in mapping["candidates"]} == {"2.4"}
    assert mapping["kpTitle"] == "自反与反自反"


def test_node_textbook_mapping_keeps_direct_node_behaviour():
    mapping = asyncio.run(get_node_textbook_mapping("rel_02_05"))

    assert mapping["found"] is True
    assert mapping["kpId"] == "K020402"
    assert mapping["kpTitle"] == "对称与反对称"
    assert [candidate["kpId"] for candidate in mapping["candidates"]] == ["K020402"]
