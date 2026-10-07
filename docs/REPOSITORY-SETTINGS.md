# GitHub repository settings handoff

The repository description, topics, and social preview are GitHub settings, not files. They must be updated by a maintainer with repository administration access; automation in this repository must not mutate them.

The machine-readable source of truth is [`.github/repository-settings-checklist.json`](../.github/repository-settings-checklist.json). For each item:

1. Apply the exact expected setting in GitHub.
2. Verify the public repository page in a signed-out browser.
3. Change only that item's `status` from `pending` to `verified` in a follow-up pull request.
4. Record verification evidence in the pull-request description; do not add credentials or private screenshots to the repository.

CI validates the checklist shape and required topics. It cannot prove that a human applied GitHub-side settings.
