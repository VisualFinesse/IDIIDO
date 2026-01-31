# Definition of Done - idoiido

The TODO list is NOT complete until ALL criteria below are met.

---

## 1. Alignment with Reference Docs ✓

**Before claiming done, verify**:

- [ ] Read the relevant reference doc(s):

  - `docs/hierarchy.md` for: monitors, context preservation, failure model, approach/attempt logic
  - `ROUTING_MAP.md` for: CTO routing, size evaluation, role responsibilities, QA failsafe
  - `docs/master.md` for: technical specifications (if applicable)

- [ ] Implementation follows the patterns in reference docs:

  - Monitor duplication pattern implemented correctly (if applicable)
  - CTO size-based routing implemented correctly (if applicable)
  - Approach/attempt definitions match role type (Dev vs Manager)
  - Context preservation mechanism works as designed
  - QA validates against product-level context (if applicable)

- [ ] Add comment in code referencing the source:
  ```python
  # Implementation based on docs/hierarchy.md - Monitor Duplication Pattern
  # Each monitor is a duplicate of parent with full parent context
  ```

---

## 2. Tests Exist and Pass ✓

### Test Requirements by Change Type:

**Model changes** (Phase 1):

- [ ] Unit tests for all model fields
- [ ] Unit tests for all model methods
- [ ] Unit tests for validation logic
- [ ] Unit tests for relationships (parent/child, monitor/agent)

**Business logic** (Phases 2-4):

- [ ] Unit tests for each function/method
- [ ] Integration tests for workflows (route → assign → execute)
- [ ] Edge case tests (exhaustion, escalation, failure)

**External integrations** (Phases 9-10):

- [ ] Mock tests (don't hit real GitLab)
- [ ] Integration tests with test GitLab instance (if available)
- [ ] Error handling tests (API failures, timeouts, rate limits)

**End-to-end workflows** (Phase 14):

- [ ] Full flow tests (CEO → CTO → ... → Dev → QA → Merge)
- [ ] Escalation flow tests (exhaust attempts → escalate up chain)
- [ ] Recovery tests (crash → respawn from checkpoint)

### Test Execution:

- [ ] Run: `python -m pytest`
- [ ] **Exit code must be 0** (all tests pass)
- [ ] **No tests skipped** (unless explicitly marked @skip with reason)
- [ ] **No warnings** about missing dependencies or deprecated code
- [ ] **Coverage**: Changed code must be covered by tests
  - New functions: 100% coverage
  - Modified functions: All new branches covered

**Test output example**:

```
✓ All tests passed (45 passed, 0 failed, 0 skipped)
✓ Exit code: 0
✓ No warnings
```

---

## 3. Code Quality Standards ✓

### Python Code Standards:

- [ ] **Type hints** on all function signatures:

  ```python
  def route_task(task: Task, cto: Agent) -> Tuple[str, Agent]:
      """CTO evaluates task size and routes to appropriate role."""
      ...
  ```

- [ ] **Docstrings** on all public functions/classes:

  ```python
  def spawn_monitor(parent: Agent, subtask: Task) -> Agent:
      """
      Spawn monitoring agent (duplicate of parent).

      Monitor holds full parent context and watches exactly one subtask.
      Based on docs/hierarchy.md - Monitor Duplication Pattern.

      Args:
          parent: Supervisor agent to duplicate
          subtask: Task the monitor will watch

      Returns:
          Monitor agent instance with parent context snapshot
      """
  ```

- [ ] **No commented-out code** (delete it, git has history)

- [ ] **No TODO comments without tracking**:

  - Bad: `# TODO: fix this later`
  - Good: `# TODO(Phase-7): Add retry logic for API failures`

- [ ] **Consistent naming**:

  - Functions: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`
  - Private: `_leading_underscore`

- [ ] **No magic numbers**:

  ```python
  # Bad
  if attempts > 2:

  # Good
  MAX_ATTEMPTS = 2  # From env or default
  if attempts > MAX_ATTEMPTS:
  ```

### Error Handling:

- [ ] **All external calls wrapped in try/except**:

  ```python
  try:
      gitlab_client.create_issue(...)
  except gitlab.exceptions.GitlabError as e:
      logger.error(f"Failed to create issue: {e}")
      raise TaskError(f"GitLab API failure: {e}")
  ```

- [ ] **Informative error messages**:

  - Bad: `raise Exception("Error")`
  - Good: `raise MonitorSpawnError(f"Cannot spawn monitor for {task.id}: parent agent {parent.id} not found")`

- [ ] **Logging at appropriate levels**:
  - `DEBUG`: Internal state, variable values
  - `INFO`: Successful operations, state transitions
  - `WARNING`: Recoverable errors, degraded performance
  - `ERROR`: Operation failures, requires attention
  - `CRITICAL`: System failures, data corruption

---

## 4. Integration with Existing Code ✓

- [ ] **No breaking changes** to existing tests (unless intentional refactor)

- [ ] **Imports work correctly**:

  ```python
  # Run this manually to verify
  python -c "from src.core.routing import route_task; print('Import OK')"
  ```

- [ ] **No circular imports** (Python should not complain on import)

- [ ] **Follows project structure**:

  - Models in `src/models/`
  - Business logic in `src/core/`
  - Agents in `src/agents/`
  - Services in `src/services/`
  - Tests in `tests/` (mirror src structure)

- [ ] **Dependencies added to requirements** (if new libraries used):
  - Update `requirements.txt` or `pyproject.toml`
  - Document why dependency is needed

---

## 5. Documentation Updated ✓

### Code Documentation:

- [ ] **Docstrings** updated for changed functions
- [ ] **Type hints** added/updated
- [ ] **Comments** explain "why", not "what":

  ```python
  # Bad comment (explains what - code already shows this)
  # Loop through tasks
  for task in tasks:

  # Good comment (explains why - not obvious from code)
  # Process tasks in priority order to prevent starvation of high-priority work
  for task in sorted(tasks, key=lambda t: t.priority):
  ```

### Project Documentation:

- [ ] **CODEMAP.md regenerated**:

  ```powershell
  python .claude\scripts\codemap.py
  ```

- [ ] **README updated** (if new features added):

  - Installation instructions current?
  - Usage examples current?
  - Architecture diagram current?

- [ ] **TODO.md updated**:
  - Current item marked complete: `- [x]`
  - Any new TODOs added (if scope expansion discovered)
  - Progress summary added (every 5 items)

---

## 6. Performance & Resource Usage ✓

- [ ] **No obvious performance issues**:

  - No O(n²) algorithms where O(n) is possible
  - No loading entire datasets into memory unnecessarily
  - No infinite loops or recursion without base case

---

## 7. Security & Safety ✓

- [ ] **No secrets in code**:

  - API tokens from environment variables
  - Passwords from .env (not committed)
  - No hardcoded credentials

- [ ] **Input validation**:

  ```python
  def create_task(description: str, task_type: TaskType) -> Task:
      if not description or len(description) < 10:
          raise ValueError("Task description must be at least 10 characters")
      if task_type not in TaskType:
          raise ValueError(f"Invalid task type: {task_type}")
      ...
  ```

- [ ] **SQL injection prevention** (if using raw SQL):

  - Use parameterized queries
  - Or use ORM (SQLAlchemy, Prisma)

- [ ] **Command injection prevention** (if calling shell):

  ```python
  # Bad
  os.system(f"git commit -m '{message}'")  # Message could contain '; rm -rf /'

  # Good
  subprocess.run(["git", "commit", "-m", message], check=True)
  ```

---

## 8. Backward Compatibility ✓

- [ ] **Database migrations** (if schema changed):

  ```powershell
  # Create migration
  alembic revision --autogenerate -m "Add monitoring_task_id to agents"

  # Apply migration
  alembic upgrade head
  ```

- [ ] **Config file changes** documented:

  - Update `.env.example` with new variables
  - Document in README or CHANGELOG

- [ ] **API changes** (if public interfaces changed):
  - Deprecate old interface first (don't break immediately)
  - Log warnings when old interface used
  - Document migration path

---

## 9. Specific idoiido Requirements ✓

### Monitor Duplication Pattern:

If implementing monitors, verify:

- [ ] Monitor is created by **duplicating parent agent**
- [ ] Monitor holds **full parent context snapshot**
- [ ] Monitor is **separate agent instance** (not shared reference)
- [ ] Monitor watches **exactly one subordinate** (one-to-one)
- [ ] Monitor can **answer subordinate questions** with parent context
- [ ] Test: Monitor responds to subordinate questions correctly
- [ ] Test: Monitor context is isolated from sibling monitors

### CTO Size-Based Routing:

If implementing routing, verify:

- [ ] CTO evaluates **task size**, not task type
- [ ] Routing uses **heuristics from ROUTING_MAP.md**
- [ ] CTO can route to **any level** (Dev, TeamLead, Arch, PM, PO)
- [ ] CTO **always spawns monitor** for routed level
- [ ] Test: Small task routes directly to Dev
- [ ] Test: Large task routes through full chain
- [ ] Test: CTO.Monitor receives escalations correctly

### Approach/Attempt Definitions:

If implementing exhaustion logic, verify:

- [ ] **Dev approach** = git branch (different strategy)
- [ ] **Dev attempt** = git commit (refinement of strategy)
- [ ] **Manager approach** = different decomposition
- [ ] **Manager attempt** = refinement of decomposition
- [ ] Test: Exhaustion after maxApproaches × maxAttempts
- [ ] Test: Escalation triggered correctly

### QA Product-Level Validation:

If implementing QA, verify:

- [ ] QA receives **Product Owner context**
- [ ] QA tests against **product acceptance criteria** (not just story)
- [ ] QA can **catch drift** (Dev implemented story but missed product requirement)
- [ ] Test: QA rejects Story that passes unit tests but fails product criteria
- [ ] Test: QA approves Story that meets product criteria

---

## 10. Final Checklist ✓

Before marking TODO item as `- [x]`:

- [ ] All sections above completed
- [ ] Tests pass: `python -m pytest` (exit code 0)
- [ ] CODEMAP regenerated: `python .claude\scripts\codemap.py `
- [ ] No warnings or errors in console
- [ ] Implementation aligns with reference docs (hierarchy.md, ROUTING_MAP.md)
- [ ] Next TODO item identified and ready to start

---

## Completion Statement Template

When marking item complete, include:

```markdown
✅ Completed TODO: [Item Description]

Reference Docs:

- Implemented based on: docs/hierarchy.md Section X / ROUTING_MAP.md Section Y
- Follows pattern: [Monitor Duplication / CTO Routing / etc.]

Tests:

- Command: python -m pytest
- Result: All tests passed (N passed, 0 failed, 0 skipped)
- Exit code: 0
- Coverage: [X%] of new code

Files Changed:

- src/core/routing.py (added route_by_size function)
- src/models/agent.py (added isMonitor field)
- tests/test_routing.py (added 8 test cases)

CODEMAP:

- Regenerated: ✓
- Files indexed: [N]

Quality:

- Type hints: ✓
- Docstrings: ✓
- Error handling: ✓
- No TODOs without tracking: ✓

Next: Proceeding to next TODO item if available
```

---

## Common Rejection Reasons

**A TODO is NOT done if**:

❌ Tests pass but reference doc pattern not followed (e.g., monitor not duplicated)
❌ Code works but has no tests
❌ Tests exist but don't cover edge cases (exhaustion, failure, escalation)
❌ Implementation contradicts hierarchy.md or ROUTING_MAP.md
❌ Magic numbers instead of configurable constants
❌ No docstrings or type hints
❌ CODEMAP not regenerated
❌ Breaking changes to existing tests (unless intentional refactor)
❌ Security issues (secrets in code, no input validation)
❌ Performance issues (O(n²) where O(n) possible)

---

## Remidoiido

**Quality > Speed**

Better to complete 5 items correctly than 20 items with bugs.

**Reference Docs are Truth**

If code contradicts hierarchy.md or ROUTING_MAP.md, the code is wrong.

**Tests are Non-Negotiable**

Untested code is broken code, just waiting to fail.

**idoiido is Complex**

This system has hierarchical context preservation, dynamic routing, monitor duplication, and drift detection. Each piece must be correct or the whole system fails.

**Take Your Time**

A TODO item might take 30 minutes or 3 hours. That's OK. Done right > done fast.
