#!/bin/sh
# Copies the files GitHub shows at the root and in each part into the docs
# tree, so mkdocs.yml can put them on the site. Run from the repository root,
# before `mkdocs build` or `mkdocs serve`. The copies are ignored by git
# (docs/.gitignore): edit the originals.
set -eu

mkdir -p docs/project docs/parts

# The root files link to docs/... and to each other by their GitHub names:
# on the site they sit in docs/project/, under new names.
root() {
  sed -e 's#](docs/#](../#g' \
      -e 's#](PR_WORKFLOW.md)#](pr-workflow.md)#g' \
      -e 's#](TESTING_STRATEGY.md)#](testing-strategy.md)#g' \
      -e 's#](CODE_OF_CONDUCT.md)#](code-of-conduct.md)#g' \
      -e 's#](CONTRIBUTING.md)#](contributing.md)#g' \
      "$1" > "docs/project/$2"
}
root CONTRIBUTING.md     contributing.md
root PR_WORKFLOW.md      pr-workflow.md
root TESTING_STRATEGY.md testing-strategy.md
root CODE_OF_CONDUCT.md  code-of-conduct.md
root SECURITY.md         security.md
root SUPPORT.md          support.md
root PROJECT_CHARTER.md  charter.md

# A part's README links to its own docs/ folder, which the site does not
# carry: those links go to GitHub.
part() {
  sed -e "s#](docs/#](https://github.com/Umbaji/HLlama/blob/develop/$1/docs/#g" \
      "$1/README.md" > "docs/parts/$1.md"
}
part bot
part backend
part admin
