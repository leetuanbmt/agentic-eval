# Agent Evaluation Report: Quickstart (mock agent)
Version: 0.1.0

- Started: 2026-10-21T05:18:48+00:00 · Duration: 0.00s
- Adapter: `mock` · Runtime: `local` · agentic-eval 0.1.0
- **Total 3** · passed 2 · failed 1 · errors 0 · timeouts 0

## Summary Scorecard

| Test Case ID | Test Case Name | Runtime (s) | Verdict | Evaluators Detail |
| --- | --- | --- | --- | --- |
| greeting | Agent prints the expected greeting | 0.00s | 🟢 PASS | **invariants**: 100.0 (PASS)<br>**exact**: 100.0 (PASS) |
| structured-report | Agent writes a structured JSON report | 0.00s | 🟢 PASS | **invariants**: 100.0 (PASS)<br>**exact**: SKIP<br>**report-json**: 100.0 (PASS) |
| missing-invariant | Agent forgets to mention the safety verdict | 0.00s | 🔴 FAIL | **invariants**: 50.0 (FAIL) |

## Detailed Evaluator Feedback

### Test Case: greeting - Agent prints the expected greeting
#### Evaluator: invariants
- **Score:** 100.0 / 100.0
- **Passed:** Yes
- **Feedback:**
```
All invariants found.
```

#### Evaluator: exact
- **Score:** 100.0 / 100.0
- **Passed:** Yes
- **Feedback:**
```
Output matches exactly.
```

### Test Case: structured-report - Agent writes a structured JSON report
#### Evaluator: invariants
- **Score:** 100.0 / 100.0
- **Passed:** Yes
- **Feedback:**
```
All invariants found.
```

#### Evaluator: exact
- **Score:** 0.0 / 100.0
- **Passed:** Skipped
- **Feedback:**
```
Skipped: no expected_outputs.exact
```

#### Evaluator: report-json
- **Score:** 100.0 / 100.0
- **Passed:** Yes
- **Feedback:**
```
JSON output matches expected fields.
```

### Test Case: missing-invariant - Agent forgets to mention the safety verdict
#### Evaluator: invariants
- **Score:** 50.0 / 100.0
- **Passed:** No
- **Feedback:**
```
Missing:
- Safety verdict
```

