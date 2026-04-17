# App Artifacts Policy

This folder is intentionally lightweight in the public repository.

Large local binary app artifacts (`.vtp`, `.sig`, `.par`, spreadsheets) are not versioned.

Reason:
- keep repository size manageable
- avoid duplicating generated/local experiment artifacts
- keep only source-level research assets in Git

If you need these local assets, keep them outside Git or under ignored paths defined in `.gitignore`.
