# Contributing

HLlama is a WhatsApp assistant for women's sexual and reproductive health,
built by Umbaji. Its three parts live in this repository:

| Directory | What it holds |
| --- | --- |
| `bot/` | the WhatsApp bot: the flows, the prompt, the tests |
| `backend/` | the API: the exchanges, the consent, the documentary base |
| `admin/` | the backoffice: the users, the questions, the corpus, the feedback |

A change that crosses two parts (a payload between the bot and the API, say)
goes in one pull request.

## Opening an issue

Every issue starts from a form (`.github/ISSUE_TEMPLATE/`): a bug report, a
feature request, or, for maintainers, a good first issue. The tracker is
public: no phone number, name or message of a real person, ever. A security
vulnerability goes through `SECURITY.md`, never an issue.

Looking for a place to start? The issues labelled
[good first issue](https://github.com/Umbaji/HLlama/labels/good%20first%20issue)
say where to look, what to change and how to know it is done.

## How a change lands

1. A branch off `develop`, named after the change.
2. A pull request to `develop`, with what changed and why.
3. The pipeline runs the tests, the lint and the build. It has to be green.
4. A merge, then the promotion to `main`, which is what deploys to production.

`develop` is the working branch; `main` is production. Nothing lands on `main`
without going through a pull request.

## The rules that matter here

- **Everything the project says about itself is in English**: the code, the
  comments, the commits, the pull requests, the documentation. The French
  belongs to the text the assistant says to the people who write to it.
- **The assistant never invents.** A figure - a dosage, a duration - comes
  from the documentary base, with its source, or it is not said.
- **A person's data is theirs.** Their number, their exchanges and the facts
  they declared are encrypted at rest, and none of it reaches the model or any
  third party in a form that identifies them.
- **The tests come with the change.** A bug fixed without a test that fails
  before it and passes after is not fixed.

## Before you push

```bash
cd bot
python -m unittest discover -s tests -p "test_*.py"
```

The backend:

```bash
python -m pytest tests/ -q
```

The backoffice:

```bash
npm run lint && npm run typecheck && npm run build
```
