---
name: audit-images
description: Audit and fix Markdown image alt text in Arm Learning Paths and install guides. Use when the user asks to review images, find deficient alt text, count faulty images, run project-level or path-level image audits, track before/after image quality, or update image alt text and captions against repository image guidance.
---

# Audit images

## Description

Audit Markdown image references in Arm Learning Paths and install guides, report deficient alt text and image syntax, and help fix alt text with useful instructional descriptions.

Use the script for repeatable inventory and counting. Use assistant judgment for semantic alt-text quality and final edits.

## Prerequisites

- Work from the repository root.
- Read `AGENTS.md` to locate shared guidance.
- Read `references/image-guidance.md` before editing image alt text, captions, or image syntax.

## Trigger

Use this skill when the user asks to:

- Audit images or alt text.
- Find placeholder, vague, missing, malformed, or duplicated alt text.
- Count faulty images across the project or inside one Path/guide.
- Track image audit counts before and after fixes.
- Fix image alt text, captions, or `#center` syntax.

## Review levels

### Project-level review

Scan all Learning Paths and install guides unless the user gives a narrower scope.

Use project-level review to:

- Count total image references and faulty image references.
- Group faults by content unit and issue type.
- Identify high-priority directories or files for cleanup.
- Produce a before/after baseline for tracking progress.

Don't mass-edit the whole project unless the user explicitly asks. Prefer reporting the project-level inventory and then fixing one Path, guide, category, or batch.

### Path/guide-level review

Scan one Learning Path directory, install guide file, or install guide directory.

Use path/guide-level review to:

- List each faulty image with file, line, image path, current alt text, caption, and issue type.
- Inspect surrounding Markdown context before changing alt text.
- View local images when visual inspection is needed.
- Fix alt text and syntax in place.
- Re-run the audit and report before/after counts.

## Workflow

1. Identify whether the requested scope is project-level or path/guide-level.
2. Run `.github/skills/audit-images/scripts/audit_images.py` on that scope.
3. Record the baseline summary: total images, faulty images, content units affected, and issue counts.
4. Depending on the request level, do the following:
  - For project-level requests, summarize the results and suggest prioritized cleanup batches unless the user asked for edits.
  - For path/guide-level edit requests, inspect the relevant Markdown context and image files.
5. Suggest rewrites for deficient alt text using `references/image-guidance.md`.
6. After the reviewer accepts suggestions, rewrite text, then re-run the audit on the same scope.
7. Report before/after counts, files changed, and any remaining issues.

## Orphan and reference-integrity workflow

Use `scripts/orphan_images.py` when the task concerns unreferenced image files,
broken local image paths, filename case mismatches, or malformed Markdown image
destinations. This is separate from the alt-text audit so existing editorial
findings do not block image-integrity checks.

1. Run the checker in report mode before deleting anything.
2. Run `scripts/orphan_images.py --fix-references` to repair deterministic
   malformed, missing, and case-mismatched references. Review any ambiguous
   references that remain instead of guessing.
3. Render the site with Hugo and pass the output to `--generated-site`. The
   checker combines tracked source references, rendered references, exact Git
   blob matches, and unresolved-reference proximity to classify candidates.
4. Run `--delete-safe` to remove only high-confidence candidates. Without a
   rendered site, only byte-identical duplicates of referenced images qualify.
5. Review only the smaller `needs review` group. Do not maintain a repository-wide
   keep-list for historical candidates.
6. Re-run the checker and Hugo build after cleanup.

Case-colliding duplicate paths are removed from the Git index without deleting
the shared worktree file on case-insensitive systems. GitHub Actions never edits
or deletes contributor files. Ordinary content PRs run the fast source check
against the base revision, so unchanged historical findings do not block a PR.
The checker still builds a repository-wide reference index to catch cross-file
effects such as deleting the only reference to an unchanged image, but it skips
the expensive Hugo render. A manual workflow run performs the full rendered
audit. Changes to layouts, themes, static assets, or Hugo configuration also
select the full audit automatically because they can alter site-wide rendering.

## Validation rules

- Treat the script as a detector, not the final authority. It flags likely problems for review.
- Use `references/image-guidance.md` as the source of truth for alt text, captions, placeholder text, `#center` syntax, and figure numbering.
- Don't replace meaningful alt text only because it is long or short; judge whether it helps the learner complete the task.
- Preserve valid local image paths and existing captions unless they are wrong, vague, or outdated.
- Preserve repository image syntax unless syntax cleanup is the target of the edit.

## Error handling

- If the script reports a missing local image path, verify whether the path is site-root-relative, file-relative, or intentionally external before changing content.
- If an image cannot be inspected, fix only issues that can be resolved from surrounding Markdown context and state the limitation.
- If project-level results are too large to edit safely, report the inventory and recommend a smaller batch.
- If the audit script and visual/context review disagree, explain the judgment and leave a short note in the final response.

## Script usage

Run a project-level audit:

```bash
python3 .github/skills/audit-images/scripts/audit_images.py
```

Run a path-level audit:

```bash
python3 .github/skills/audit-images/scripts/audit_images.py content/learning-paths/servers-and-cloud-computing/example-path
```

Write JSON for tracking:

```bash
python3 .github/skills/audit-images/scripts/audit_images.py --format json --output image-audit.json
```

Report image-integrity problems without changing files:

```bash
python3 .github/skills/audit-images/scripts/orphan_images.py
```

Fail when any current problems exist:

```bash
python3 .github/skills/audit-images/scripts/orphan_images.py --check
```

Fail only for problems introduced since a Git reference:

```bash
python3 .github/skills/audit-images/scripts/orphan_images.py \
  --check --changed-since origin/main
```

Apply deterministic reference repairs in bulk:

```bash
python3 .github/skills/audit-images/scripts/orphan_images.py --fix-references
```

Build the site and classify candidates with independent rendered evidence:

```bash
hugo --destination /tmp/arm-learning-paths-image-integrity
python3 .github/skills/audit-images/scripts/orphan_images.py \
  --generated-site /tmp/arm-learning-paths-image-integrity
```

Delete only candidates supported by the available confidence evidence:

```bash
python3 .github/skills/audit-images/scripts/orphan_images.py \
  --generated-site /tmp/arm-learning-paths-image-integrity \
  --delete-safe
```

Use the **Image integrity** workflow's **Run workflow** control and select
`full` for a read-only Hugo-backed audit or `fast` for a change-aware source
audit. Both modes remain inside the same workflow and publish their report in
the run summary and as a downloadable artifact. Normal pull requests and pushes
select the appropriate mode automatically.
