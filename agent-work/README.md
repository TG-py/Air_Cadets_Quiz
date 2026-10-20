# Agent work notes

Working documentation for AI agents and contributors building on RAFAC
Questions. The source code, the running interface, and the test suite are the
authority; these notes explain intent and point to the right files so you do not
have to reconstruct the product from individual screens.

Start with [`../AGENTS.md`](../AGENTS.md) for commands and the project layout,
then open the note below that matches the task.

## Index

| Folder | Document | Use it for |
| --- | --- | --- |
| `product/` | [`FEATURE-GUIDE.md`](product/FEATURE-GUIDE.md) | Roles, features, workflows, and the product rules that must not regress |
| `ui/` | [`UI-DESIGN-RULES.md`](ui/UI-DESIGN-RULES.md) | Visual language, tokens, layout, and accessibility for interface work |
| `ui/` | [`MOBILE-RESPONSIVE-DIFFERENCES.md`](ui/MOBILE-RESPONSIVE-DIFFERENCES.md) | Desktop versus phone layout and interaction differences |
| `engineering/` | [`ARCHITECTURE.md`](engineering/ARCHITECTURE.md) | Module map, request lifecycle, data model, route/access model, conventions, and how to extend safely |
| `engineering/` | [`IMPLEMENTED-IMPROVEMENTS.md`](engineering/IMPLEMENTED-IMPROVEMENTS.md) | History of accepted changes and their verification status |

## How to use these notes

- For a feature change, read `product/FEATURE-GUIDE.md` first, then the relevant
  part of `engineering/ARCHITECTURE.md` before editing code.
- For any visual or responsive change, read both `ui/` documents before
  touching markup or CSS.
- After a change, add or update a case in `tests/` and record accepted work in
  `engineering/IMPLEMENTED-IMPROVEMENTS.md`.
- Treat older labels you may find in the README or hidden markup as historical.
  Confirm current navigation and behaviour in `static/index.html` and
  `static/app.js`.

## Keeping these notes current

- Update the matching note in the same change that alters behaviour, a route, a
  module, or a verification result.
- Keep `FEATURE-GUIDE.md` about the product, and `ARCHITECTURE.md` about the
  code. Do not duplicate the code map outside `ARCHITECTURE.md`.
- When the end-to-end suite count changes, update the verification line in
  `engineering/IMPLEMENTED-IMPROVEMENTS.md`.
