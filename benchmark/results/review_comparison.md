
# AI Review Benchmark Results

## 1. Project Information

- Project: AI Review Benchmark
- Repository: RetailPulse-AI
- Pull Request: #1
- Base branch: main
- Benchmark branch: benchmark/proofline-ai-review
- Objective: Evaluate AI code reviewers on identical Python code changes.

## 2. Reviewers Evaluated

| Reviewer | Review Method | Findings Reported |
|---|---|---:|
| Proofline | Automated GitHub PR review | 2 |
| GitHub Copilot Chat | Manual AI review | 4 |
| Claude | Manual source-code review | 6 |

## 3. Findings Comparison

| Finding | Proofline | Copilot | Claude |
|---|---|---|---|
| Cross-year monthly grouping | Found | Found | Found |
| Missing invoice dates | Found | Found | Found |
| Revenue validation | Not found | Found | Found |
| Strict xfail test concerns | Not found | Found | Found |
| Missing successful aggregation tests | Not found | Not found | Found |
| Missing-column test coverage | Not found | Not found | Found |

## 4. Technical Findings

### Finding 1: Cross-Year Grouping

The implementation uses `%m` instead of `%Y-%m`.

Transactions from January 2024 and January 2025 are combined into one revenue total.

Recommended correction:
Use a year-aware monthly grouping key.

### Finding 2: Missing Invoice Dates

Null dates can be converted to NaT and silently excluded during groupby aggregation.

Recommended correction:
Explicitly validate missing dates before aggregation.

### Finding 3: Revenue Validation

Revenue values are not explicitly checked for missing or non-numeric values.

Recommended correction:
Validate revenue values before calculating monthly totals.

### Finding 4: Xfail Test Management

The known cross-year defect is documented using pytest xfail.

The strict xfail should be removed when the defect is fixed. During the benchmark, restricting expected failures to assertion failures would make the test more reliable.

### Finding 5: Missing Success-Path Tests

The benchmark lacks a normal passing test that verifies successful monthly revenue aggregation.

### Finding 6: Missing-Column Test Coverage

The existing test checks for a missing Revenue column but does not separately cover missing InvoiceDate or both missing columns.

## 5. Initial Benchmark Observations

- All three reviewers detected the cross-year grouping defect.
- All three identified the missing-date handling issue.
- Copilot and Claude identified revenue-validation concerns.
- Copilot and Claude raised concerns about xfail handling.
- Claude additionally identified two test-coverage gaps.
- Proofline completed its automated review in 56 seconds.

## 6. Methodology

- All reviewers were given the same benchmark code changes.
- Proofline performed an automated GitHub Pull Request review.
- Copilot Chat and Claude were manually prompted.
- Each reviewer's findings were compared against the supplied source code and reproducible examples.
- Findings were grouped into common and reviewer-specific categories.

Note: Finding counts are raw reported findings, not accuracy scores. False positives and precision have not yet been measured against a finalized ground-truth dataset.

## 7. Next Steps

1. Verify all candidate findings with automated tests.
2. Correct the monthly grouping logic.
3. Add date and revenue validation.
4. Improve regression test coverage.
5. Run the complete pytest suite.
6. Run Proofline again after the fixes.
7. Record final results and evidence.


## 8. Post-Fix Verification Results

### Implementation Improvements
- Replaced month-only grouping with year-aware monthly grouping.
- Added missing and invalid invoice date validation.
- Added numeric revenue validation.
- Added missing and non-finite revenue validation.
- Improved automated regression tests.

### Automated Test Results

Command:
python -m pytest -v

| Metric | Result |
|---|---:|
| Total tests collected | 54 |
| Passed | 54 |
| Failed | 0 |
| Skipped | 0 |
| Execution time | 5.75 seconds |

### Test Environment
- Operating System: Windows
- Python: 3.14.6
- Pytest: 9.2.0

### Verification Conclusion

All 54 project tests passed after installing
the required project dependencies.

The benchmark regression tests and existing
RetailPulse application tests both passed.

The corrected implementation addresses the
confirmed date-grouping and input-validation
issues identified during the initial review.

