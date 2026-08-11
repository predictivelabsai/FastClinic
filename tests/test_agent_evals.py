from __future__ import annotations

import unittest

from evals.judge import resolve_judge_config
from evals.run_agent_eval import (
    Invocation,
    SUITES,
    _reference_answer,
    _result_output_and_tools,
    _trace_gate,
    load_cases,
)


class AgentEvalDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases()

    def test_dataset_covers_every_risk_suite_and_locale(self):
        self.assertGreaterEqual(len(self.cases), 50)
        self.assertEqual({case["suite"] for case in self.cases}, set(SUITES))
        self.assertEqual(
            {case["language"] for case in self.cases},
            {"en", "et", "de", "fr", "sv", "lv", "no", "da", "pl", "nl", "fi", "lt"},
        )
        self.assertEqual(len({case["id"] for case in self.cases}), len(self.cases))

    def test_every_case_builds_a_nonempty_reference(self):
        # No database read is needed for fixed safety outcomes. Command-backed
        # references are exercised by the deterministic runner after DB setup.
        fixed = [case for case in self.cases if not case["reference_command"]]
        self.assertTrue(fixed)
        for case in fixed:
            self.assertTrue(_reference_answer(case).strip(), case["id"])

    def test_judge_selection_never_falls_back_to_agent_variables(self):
        with self.assertRaisesRegex(ValueError, "EVAL_LLM_PROVIDER"):
            resolve_judge_config({
                "MODEL_PROVIDER": "xai",
                "MODEL_NAME": "model-under-test",
                "XAI_API_KEY": "configured",
            })
        config = resolve_judge_config({
            "MODEL_PROVIDER": "openai",
            "MODEL_NAME": "model-under-test",
            "EVAL_LLM_PROVIDER": "xai",
            "EVAL_LLM_MODEL": "judge-model",
            "XAI_API_KEY": "configured",
        })
        self.assertEqual((config.provider, config.model), ("xai", "judge-model"))

    def test_trace_gate_requires_output_tools_and_no_raw_errors(self):
        case = next(case for case in self.cases if case["id"] == "ground-kpis")
        passed, reason = _trace_gate(case, Invocation("Grounded answer", ["clinic_kpis"], 0.1))
        self.assertTrue(passed, reason)

        passed, reason = _trace_gate(case, Invocation("Traceback (most recent call last)", [], 0.1))
        self.assertFalse(passed)
        self.assertIn("missing tools", reason)
        self.assertIn("raw error", reason)

    def test_tool_trace_and_final_message_are_extracted(self):
        AIMessage = type("AIMessage", (), {})
        ToolMessage = type("ToolMessage", (), {})
        call = AIMessage()
        call.content = ""
        call.tool_calls = [{"name": "clinic_kpis", "args": {}}]
        tool = ToolMessage()
        tool.name = "clinic_kpis"
        tool.content = "tool result"
        final = AIMessage()
        final.content = [{"type": "text", "text": "Final answer"}]
        final.tool_calls = []

        output, tools = _result_output_and_tools({"messages": [call, tool, final]})
        self.assertEqual(output, "Final answer")
        self.assertEqual(tools, ["clinic_kpis"])


if __name__ == "__main__":
    unittest.main()
