import unittest

from fastapi.testclient import TestClient

from algorithm_tools.code_generator import generate_discrete_math_code
from algorithm_tools.graph_tools import check_bipartite, dijkstra_shortest_path, generate_hasse_diagram
from algorithm_tools.logic_tools import convert_normal_forms, simplify_formula
from algorithm_tools.main import app
from algorithm_tools.relation import analyze_relation
from algorithm_tools.set_tools import calculate_set_operation
from algorithm_tools.truth_table import generate_truth_table


class RelationTests(unittest.TestCase):
    def test_equivalence_relation(self):
        result = analyze_relation(
            [
                [1, 0, 1],
                [0, 1, 0],
                [1, 0, 1],
            ]
        )

        self.assertTrue(result["reflexive"])
        self.assertFalse(result["irreflexive"])
        self.assertTrue(result["symmetric"])
        self.assertFalse(result["antisymmetric"])
        self.assertTrue(result["transitive"])

    def test_partial_order_relation(self):
        result = analyze_relation(
            [
                [1, 1, 1],
                [0, 1, 1],
                [0, 0, 1],
            ]
        )

        self.assertTrue(result["reflexive"])
        self.assertFalse(result["symmetric"])
        self.assertTrue(result["antisymmetric"])
        self.assertTrue(result["transitive"])

    def test_invalid_matrix(self):
        with self.assertRaises(ValueError):
            analyze_relation([[1, 0], [0]])


class TruthTableTests(unittest.TestCase):
    def test_implication(self):
        table = generate_truth_table("p -> q")
        results = [row["result"] for row in table["rows"]]

        self.assertEqual(table["variables"], ["p", "q"])
        self.assertEqual(results, [True, True, False, True])

    def test_parentheses_and_not(self):
        table = generate_truth_table("(p and q) or not r")

        self.assertEqual(table["variables"], ["p", "q", "r"])
        self.assertEqual(len(table["rows"]), 8)

    def test_invalid_expression(self):
        with self.assertRaises(ValueError):
            generate_truth_table("p and")

    def test_operator_precedence(self):
        table = generate_truth_table("p -> q and r")
        matching_row = next(
            row for row in table["rows"]
            if row["values"] == {"p": False, "q": False, "r": False}
        )
        self.assertTrue(matching_row["result"])


class LogicToolTests(unittest.TestCase):
    def test_formula_simplification(self):
        response = simplify_formula("(p and q) or (p and not q)")
        self.assertEqual(response["result"]["simplified"], "p")
        self.assertTrue(response["steps"])

    def test_principal_normal_forms(self):
        response = convert_normal_forms("p -> q")
        result = response["result"]
        self.assertEqual(result["minterm_indices"], [0, 1, 3])
        self.assertEqual(result["maxterm_indices"], [2])
        self.assertEqual(result["principal_cnf"], "(not p or q)")


class SetToolTests(unittest.TestCase):
    def test_set_operations(self):
        response = calculate_set_operation([1, 2, 2], "union", [2, 3])
        self.assertEqual(response["result"]["value"], [1, 2, 3])

    def test_power_set(self):
        response = calculate_set_operation(["a", "b"], "power_set")
        self.assertEqual(len(response["result"]["value"]), 4)


class GraphToolTests(unittest.TestCase):
    def test_hasse_diagram_removes_transitive_edges(self):
        response = generate_hasse_diagram(
            [1, 2, 4],
            relation=[[1, 1], [2, 2], [4, 4], [1, 2], [2, 4], [1, 4]],
        )
        edges = response["result"]["edges"]
        self.assertEqual(len(edges), 2)
        self.assertNotIn({"source": "1", "target": "4", "relation": "covers"}, edges)

    def test_hasse_divisibility_rebuilds_relation_for_new_elements(self):
        response = generate_hasse_diagram(
            [1, 2, 3, 6, 12], relation_type="divisibility"
        )
        result = response["result"]

        self.assertEqual(result["relation_type"], "divisibility")
        self.assertIn(
            {"source": "3", "target": "6", "relation": "covers"},
            result["edges"],
        )
        self.assertNotIn(
            {"source": "1", "target": "12", "relation": "covers"},
            result["edges"],
        )

    def test_hasse_subset_mode(self):
        response = generate_hasse_diagram(
            [[], [1], [2], [1, 2]], relation_type="subset"
        )
        self.assertEqual(len(response["result"]["edges"]), 4)

    def test_dijkstra(self):
        response = dijkstra_shortest_path(
            [["A", "B", 2], ["A", "C", 7], ["B", "C", 1]],
            "A",
            "C",
        )
        self.assertEqual(response["result"]["path"], ["A", "B", "C"])
        self.assertEqual(response["result"]["distance"], 3)

    def test_dijkstra_rejects_negative_weight(self):
        with self.assertRaises(ValueError):
            dijkstra_shortest_path([[0, 1, -1]], 0, 1)

    def test_bipartite_partition(self):
        response = check_bipartite(
            [
                [0, 1, 0, 1],
                [1, 0, 1, 0],
                [0, 1, 0, 1],
                [1, 0, 1, 0],
            ]
        )
        self.assertTrue(response["result"]["is_bipartite"])
        self.assertEqual(response["result"]["partitions"], {"left": [0, 2], "right": [1, 3]})

    def test_odd_cycle_is_not_bipartite(self):
        response = check_bipartite([[0, 1, 1], [1, 0, 1], [1, 1, 0]])
        self.assertFalse(response["result"]["is_bipartite"])


class CodeGenerationTests(unittest.TestCase):
    def test_python_dijkstra_template(self):
        response = generate_discrete_math_code("求带权图的最短路径", "python")
        self.assertEqual(response["result"]["problem_type"], "dijkstra")
        self.assertIn("def dijkstra", response["result"]["code"])

    def test_qwen_generation_uses_complete_problem(self):
        class FakeLLM:
            def __init__(self):
                self.messages = []

            def generate(self, messages):
                self.messages = messages
                return """```python
numbers = [12, 18]
print(6)
```"""

        llm = FakeLLM()
        response = generate_discrete_math_code(
            "编写程序求 12 和 18 的最大公约数",
            "python",
            use_llm=True,
            llm_client=llm,
        )

        self.assertEqual(response["result"]["problem_type"], "general")
        self.assertEqual(response["result"]["generation_mode"], "qwen")
        self.assertIn("12 和 18", llm.messages[1]["content"])
        self.assertIn("numbers = [12, 18]", response["result"]["code"])

    def test_known_problem_falls_back_when_llm_is_unavailable(self):
        class FailingLLM:
            def generate(self, messages):
                raise RuntimeError("offline")

        response = generate_discrete_math_code(
            "求带权图的最短路径",
            "python",
            use_llm=True,
            llm_client=FailingLLM(),
        )

        self.assertEqual(response["result"]["generation_mode"], "verified_template")
        self.assertIn("def dijkstra", response["result"]["code"])

    def test_dijkstra_fallback_embeds_problem_edges_and_endpoints(self):
        response = generate_discrete_math_code(
            "给定 A-B 权重为2、A-C权重为7、B-C权重为1，求 A 到 C 的最短路径和距离",
            "python",
            use_llm=False,
        )
        code = response["result"]["code"]

        self.assertIn("'A': [('B', 2), ('C', 7)]", code)
        self.assertIn("dijkstra(graph, 'A', 'C')", code)
        self.assertIn("最短路径", code)


class ExtendedApiTests(unittest.TestCase):
    client = TestClient(app)

    def test_common_request_and_response_shape(self):
        response = self.client.post(
            "/tools/formula-simplify",
            json={"params": {"expression": "p or (p and q)"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"result", "steps", "explanation"})

    def test_invalid_tool_input_returns_400(self):
        response = self.client.post(
            "/tools/dijkstra",
            json={"params": {"edges": [["A", "B", -2]], "start": "A", "end": "B"}},
        )
        self.assertEqual(response.status_code, 400)

    def test_truth_table_supports_legacy_and_standard_requests(self):
        legacy = self.client.post("/tools/truth-table", json={"expression": "p -> q"})
        standard = self.client.post(
            "/tools/truth-table",
            json={"params": {"expression": "p -> q"}},
        )
        self.assertEqual(legacy.status_code, 200)
        self.assertIn("rows", legacy.json())
        self.assertEqual(standard.status_code, 200)
        self.assertEqual(set(standard.json()), {"result", "steps", "explanation"})

    def test_relation_supports_standard_request(self):
        response = self.client.post(
            "/tools/relation-properties",
            json={"params": {"matrix": [[1, 0], [0, 1]]}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["result"]["reflexive"])

    def test_hasse_api_can_build_divisibility_relation_from_elements(self):
        response = self.client.post(
            "/tools/hasse-diagram",
            json={
                "params": {
                    "elements": [1, 2, 3, 6],
                    "relation_type": "divisibility",
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["relation_type"], "divisibility")

    def test_code_api_infers_problem_type_without_dropdown(self):
        response = self.client.post(
            "/tools/code-generate",
            json={
                "params": {
                    "problem": "求带权图中两个顶点的最短路径",
                    "language": "python",
                    "use_llm": False,
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["problem_type"], "dijkstra")
        self.assertEqual(result["problem_type_source"], "automatic")


if __name__ == "__main__":
    unittest.main()
