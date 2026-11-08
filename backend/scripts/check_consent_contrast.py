"""Fail the build when a colour pair of the consent page drops below WCAG AA.

The pairs are read from the stylesheet itself, so a token edited in
`static/consent/consent.css` is checked here without touching this file.

Usage: python scripts/check_consent_contrast.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "consent" / "consent.css"

AA_NORMAL = 4.5
AA_LARGE = 3.0

# (foreground token, background token, label, threshold)
PAIRS = (
    ("--c-ink", "--c-surface", "body text on a card", AA_NORMAL),
    ("--c-ink", "--c-canvas", "body text on the canvas", AA_NORMAL),
    ("--c-ink-muted", "--c-surface", "muted text on a card", AA_NORMAL),
    ("--c-ink-muted", "--c-canvas", "muted text on the canvas", AA_NORMAL),
    ("--c-ink-muted", "--c-surface-sunken", "muted text on a sunken block", AA_NORMAL),
    ("--c-on-primary", "--c-primary", "accept button label", AA_NORMAL),
    ("--c-primary", "--c-surface", "links and the refuse outline", AA_NORMAL),
    ("--c-primary", "--c-primary-soft", "section number and success panel", AA_NORMAL),
    ("--c-accent", "--c-accent-soft", "version chip and warnings", AA_NORMAL),
    ("--c-danger", "--c-danger-soft", "error panel", AA_NORMAL),
    ("--c-canvas", "--c-ink", "jump-to-choice pill", AA_NORMAL),
    # Non-text contrast (WCAG 1.4.11): the parts a user must be able to make out.
    # The checkbox box and the refuse button outline are both --c-ink-muted on a
    # card, covered above. Card hairlines and the progress track are decorative
    # and carry no information, so they are deliberately not checked.
    ("--c-primary", "--c-hairline", "reading progress fill on its track", AA_LARGE),
)


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _ratio(foreground: str, background: str) -> float:
    light, dark = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _tokens(css: str, block: str) -> dict[str, str]:
    return dict(re.findall(r"(--c-[a-z-]+):\s*(#[0-9A-Fa-f]{6})", block))


def _blocks(css: str) -> tuple[dict[str, str], dict[str, str]]:
    """Read the light tokens and both dark blocks, and refuse to let them drift.

    Dark values are declared twice, once for the device preference and once for
    the reader's own choice in the footer. Checking only one of them would let a
    manual dark theme fail AA unnoticed.
    """
    root = re.search(r":root\s*\{(.*?)\}", css, re.S)
    by_preference = re.search(
        r'prefers-color-scheme:\s*dark.*?:root:not\(\[data-theme="light"\]\)\s*\{(.*?)\}', css, re.S
    )
    by_choice = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\}', css, re.S)
    if not root or not by_preference or not by_choice:
        raise SystemExit("could not find the light and dark token blocks")

    preference_tokens = _tokens(css, by_preference.group(1))
    choice_tokens = _tokens(css, by_choice.group(1))
    if preference_tokens != choice_tokens:
        differing = sorted(
            key for key in set(preference_tokens) | set(choice_tokens)
            if preference_tokens.get(key) != choice_tokens.get(key)
        )
        raise SystemExit("the two dark token blocks differ on: " + ", ".join(differing))

    light_tokens = _tokens(css, root.group(1))
    return light_tokens, {**light_tokens, **choice_tokens}


def _check(tokens: dict[str, str], scheme: str) -> list[str]:
    failures: list[str] = []
    print(f"\n{scheme}")
    for foreground, background, label, threshold in PAIRS:
        fg = tokens.get(foreground)
        bg = tokens.get(background)
        if not fg or not bg:
            failures.append(f"{scheme}: unknown token in pair {foreground}/{background}")
            continue

        ratio = _ratio(fg, bg)
        ok = ratio >= threshold
        print(f"  {'OK  ' if ok else 'FAIL'} {ratio:5.2f}:1  (min {threshold})  {label}")
        if not ok:
            failures.append(f"{scheme}: {label} is {ratio:.2f}:1, below {threshold}")
    return failures


def main() -> int:
    css = CSS_PATH.read_text(encoding="utf-8")
    light_tokens, dark_tokens = _blocks(css)

    failures = _check(light_tokens, "light")
    failures += _check(dark_tokens, "dark")

    if failures:
        print("\nContrast check failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nEvery pair meets WCAG AA.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
