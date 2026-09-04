import unittest
from types import SimpleNamespace

from graph2.graph_2 import (
    decide_to_generate,
    grade_generation_v_documents_and_question,
    route_question,
)


class FakeChain:
    def __init__(self, value, attribute):
        self.value = value
        self.attribute = attribute

    def invoke(self, _inputs):
        return SimpleNamespace(**{self.attribute: self.value})


class GraphPolicyTest(unittest.TestCase):
    def test_document_decision_routes_are_deterministic(self):
        self.assertEqual(decide_to_generate({"documents": ["doc"]}), "generate")
        self.assertEqual(decide_to_generate({"documents": [], "transform_count": 0}), "transform_query")
        self.assertEqual(decide_to_generate({"documents": [], "transform_count": 2}), "web_search")

    def test_question_router_maps_all_supported_sources(self):
        for source in ("vectorstore", "web_search", "direct_answer"):
            with self.subTest(source=source):
                result = route_question(
                    {"question": "test"},
                    router_chain=FakeChain(source, "datasource"),
                )
                self.assertEqual(result, source)

    def test_grounded_and_useful_answer_terminates(self):
        state = {"question": "q", "documents": ["doc"], "generation": "answer"}

        result = grade_generation_v_documents_and_question(
            state,
            hallucination_grader=FakeChain("yes", "binary_score"),
            answer_grader=FakeChain("yes", "binary_score"),
        )

        self.assertEqual(result, "useful")

    def test_grounded_but_unhelpful_answer_rewrites(self):
        state = {"question": "q", "documents": ["doc"], "generation": "answer"}

        result = grade_generation_v_documents_and_question(
            state,
            hallucination_grader=FakeChain("yes", "binary_score"),
            answer_grader=FakeChain("no", "binary_score"),
        )

        self.assertEqual(result, "not useful")

    def test_unsupported_answer_honors_retry_limit(self):
        grader = FakeChain("no", "binary_score")
        base_state = {"question": "q", "documents": ["doc"], "generation": "answer"}

        retry = grade_generation_v_documents_and_question(
            {**base_state, "hallucination_count": 1},
            hallucination_grader=grader,
        )
        exhausted = grade_generation_v_documents_and_question(
            {**base_state, "hallucination_count": 2},
            hallucination_grader=grader,
        )

        self.assertEqual(retry, "not supported")
        self.assertEqual(exhausted, "not supported exhausted")


if __name__ == "__main__":
    unittest.main()
