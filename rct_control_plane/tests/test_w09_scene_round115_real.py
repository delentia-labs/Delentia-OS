"""Amendment 10: the W09 agent world answers the path the model actually checks."""
from research.daaes import w09_child as w


def test_a_committed_order_is_placed_with_or_without_extension_and_dot_slash():
    placed = ["order-1", "order-2"]
    for path in ("reports/order-2", "reports/order-2.txt", "./reports/order-2.txt", " reports/order-2.json "):
        assert w.read_answer(path, placed) == "placed", path


def test_an_order_not_committed_does_not_exist():
    assert w.read_answer("reports/order-3", ["order-1", "order-2"]) == "no such file: order-3 has not been placed yet"
    assert w.read_answer("reports/order-3.txt", []) == "no such file: order-3 has not been placed yet"
    assert w.read_answer("./reports/order-2.json", ["order-1"]) == "no such file: order-2 has not been placed yet"


def test_the_list_file_still_works_and_other_paths_do_not_exist():
    assert w.read_answer("orders/placed.txt", ["order-1", "order-2"]) == "order-1\norder-2"
    assert w.read_answer("orders/placed.txt", []) == ""
    for path in ("README.md", "reports/", "reports/../orders/x", "reports/other-1", "reports/order-x", "storage/old_store.py"):
        assert w.read_answer(path, ["order-1"]) == "no such file", path


def test_the_tool_description_names_the_path_and_the_scene_version():
    desc = w.TOOLS[0].description
    assert "reports/<order id>.txt" in desc and "orders/placed.txt" in desc and w.SCENE_VERSION == 4
