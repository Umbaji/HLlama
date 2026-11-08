# Tests

## What the tests are for

The assistant is in the middle of somebody's health question. A test that
catches a wrong dosage, a wrong date or a leaked identifier is worth more than
a hundred tests of the formatting.

## Where they are

Each command runs from its part's directory; the pipeline runs it whenever that
part changes (`bot-tests.yml`, `backend-tests.yml`, `admin-checks.yml`).

| Directory | The command | The suite |
| --- | --- | --- |
| `bot/` | `python -m unittest discover -s tests -p "test_*.py"` | the flows, the prompt, the contract |
| `backend/` | `python -m pytest tests/ -q` | the API, the services, the migrations |
| `admin/` | `npm run lint && npm run typecheck && npm run build` | the types and the build |

## What a test asserts here

- **The flow**: the number and the date that reach the backend are the ones
  the person gave, and nothing is created before she confirms.
- **The truth of the assistant**: a figure appears only when a passage of the
  documentary base carries it, and the prompt says so.
- **The privacy**: the analysis of the usage holds no number, no identifier and
  no sentence of somebody.
- **The migrations**: the chain has exactly one head, and every migration
  hangs on a revision that exists. A second head stops the application from
  starting at all, so the chain is read by a test.

## The clock and the network

The tests own their clock and never reach the network. A date is given, not
waited for; the provider is replaced by a double that records what it was
asked.

## Sample test cases

A few of the cases the suites hold, as they read: what is given, what is done,
what must come out.

| Test | Given | When | Expected |
| --- | --- | --- | --- |
| `bot/tests/test_consent_gate.py` `test_backend_down_fails_closed` | the API cannot be reached | a message arrives | the person gets the "service unavailable" text; nothing reaches the model |
| `bot/tests/test_consent_gate.py` `test_server_error_and_garbage_fail_closed` | the API answers 500, an empty body, or a status it does not know (`"maybe"`) | the bot checks the consent | the consent is treated as not given |
| `bot/tests/test_consent_gate.py` `test_phone_is_only_in_the_body` | an accepted consent | the bot asks the API for the status | the phone number is in the JSON body, never in the URL (URLs end up in logs) |
| `backend/tests/test_reminders.py` `test_due_claims_reminder_once` | one reminder due now | the bot polls `/api/bot/reminders/due` twice | the first poll returns it, with its time zone `Africa/Lome`, in status `sending`; the second returns nothing |
| `backend/tests/test_migrations.py` `test_the_chain_has_exactly_one_head` | the Alembic migrations | the chain is read | it has one head, or the test names the heads |

A new test reads the same way: its name says what must hold, in a sentence.

## The data structures

The tables the tests create and assert on (`backend/models/`). Every person is
known by a `pseudo_id`: a keyed digest of the phone number
(`backend/helpers/anonymity.py`), the same in the bot and the API, from which
the number cannot be recovered. A phone number that is kept is stored
encrypted (`telnumber`).

| Table (model) | What a row is | Its states |
| --- | --- | --- |
| `users` (`UserModel`) | a person, or a member of the team | `is_active`, `deleted_at` once forgotten |
| `consent_records` (`ConsentRecordModel`) | one consent decision, with the version of the policy it answered | `accepted`, `refused`; the latest one counts |
| `reminders` (`ReminderModel`) | a reminder: its kind, its message, its date, its repetition | `pending` -> `sending` (claimed by a bot poll) -> `sent` or `failed`; `sent` -> `undelivered`; `cancelled` |

The rest (`feedback`, `health_fact`, `knowledge`, `question`, `service_miss`,
`activity_log`) follows the same rules: `pseudo_id`, never a clear number.

The test data is built the same way in every suite:

- **The bot**: fixed fake numbers (`22890000000` for her, `22890000102` for
  somebody else), the structured answer the model would give
  (`request_type`, `scheduled_at`...) written by hand, and `requests.post`
  replaced by a fake that answers per URL.
- **The API**: a fresh in-memory SQLite database per test
  (`backend/tests/conftest.py`), the FastAPI `TestClient`, and secrets that
  are obviously fake (`test-pseudo-id-secret`).

No test uses a real phone number, a real name of a person who wrote to the
service, or a real key.

## The pull request

A change and its tests travel together, through the flow in
[PR_WORKFLOW.md](PR_WORKFLOW.md): a branch off `develop`, a pull request whose
checks above must be green, then the promotion to `main`. A bug is fixed with
a test that fails before the fix and passes after.

## Coverage

Every run of the pipeline measures the coverage of the part it tests, writes
the figure in the run's summary (Actions -> the run -> Summary), keeps the
HTML report for 90 days as an artifact (`bot-coverage`, `backend-coverage`,
`admin-coverage`), and fails below 15 % of the statements.

| Part | What is measured |
| --- | --- |
| `backend/` | the application, not `tests/` or `alembic/` (`backend/.coveragerc`) |
| `bot/` | the application, not `tests/` (`bot/.coveragerc`) |
| `admin/` | every file of `src/`, pages included (`admin/vitest.config.mts`) |

The same command, locally:

```bash
cd backend && python -m pytest tests/ --cov && python -m coverage report
cd bot && python -m coverage run -m unittest discover -s tests -p "test_*.py" && python -m coverage report
cd admin && npm run test:coverage
```

The back office's tests (`src/**/*.test.ts(x)`, Vitest) replace the network
under the API client (`src/test/fake-api.ts`) so every request goes through
the real interceptors, and render the components with the application's real
messages (`src/test/intl.tsx`): a translation key that does not exist fails
the test.
