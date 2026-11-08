# Pull requests

## The path of a change

```
a branch off develop  ->  a pull request to develop  ->  a merge
                                                          |
                                                          v
                                             a pull request to main  ->  a merge
                                                          |
                                                          v
                                                     production
```

`develop` is where the work happens; `main` is what production runs. A change
reaches production by two pull requests, never by a push.

## What a pull request holds

- **Why**: the problem, in one paragraph. Not the diff.
- **What**: the change, and what it does not do.
- **How it was checked**: the tests that were run, and what they prove.
- **The contract**: when a payload, an endpoint or a prompt changes, the
  contract changes with it, in the same pull request.

## The checks

| Part | The pipeline runs, when that part changes |
| --- | --- |
| `bot/` | the unittest suite |
| `backend/` | pytest |
| `admin/` | the type check, the lint, the build |
| all | the secret guard, on every push and pull request |

Deployment is outside this repository: the pipeline runs the checks above,
and a maintainer deploys the parts that changed from their own platform.

## From develop to main

1. **A change**: a branch off `develop`, named after the change
   (`feat/...`, `fix/...`, `docs/...`, `test/...`), and a pull request to
   `develop`. Nothing is pushed to `develop` or `main` directly.
2. **Its merge**: once the checks of the parts it touches are green, the
   author or a maintainer merges it into `develop`. The author may ask a
   teammate for a review; it is not required.
3. **A release**: a maintainer opens a pull request from `develop` to `main`,
   reads what it brings, and merges it with a merge commit, never a squash, so
   `main` and `develop` keep the same history. A maintainer then deploys the
   parts that changed from their own platform.
4. **An urgent fix** may go to `main` by its own pull request; it is merged
   back into `develop` right after, or the next release conflicts.

Production always runs what was merged into `main`; deployment is triggered by
a maintainer outside this repository.

## The secrets

`scripts/check_secrets.py` refuses a commit or a push that carries a token, a
key or a password. The hooks that run it are installed with
`scripts/install-hooks.sh`, and the pipeline runs it again on every push,
because a hook can be skipped.
