from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "orphan_images.py"
SPEC = importlib.util.spec_from_file_location("orphan_images", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
orphan_images = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = orphan_images
SPEC.loader.exec_module(orphan_images)


def snapshot(files: dict[str, str | bytes]) -> orphan_images.Snapshot:
    tracked: dict[str, str] = {}
    text: dict[str, str] = {}
    for path, content in files.items():
        data = content.encode("utf-8") if isinstance(content, str) else content
        tracked[path] = hashlib.sha1(data).hexdigest()
        if not orphan_images.is_image_path(path):
            text[path] = data.decode("utf-8")
    return orphan_images.Snapshot(files=tracked, text=text)


class OrphanImagesTests(unittest.TestCase):
    def test_recognizes_supported_reference_formats(self) -> None:
        guide = """---
diagram: frontmatter.png
---

![Convolution diagram#center](images/conv.jpg "Example of a (7,7) Conv node")
<img src="images/html.png" alt="HTML example">
{{< tab img_src="/learning-paths/category/example/images/hugo.webp">}}
"""
        analysis = orphan_images.analyze(
            snapshot(
                {
                    "content/learning-paths/category/example/guide.md": guide,
                    "content/learning-paths/category/example/frontmatter.png": b"frontmatter",
                    "content/learning-paths/category/example/images/conv.jpg": b"markdown",
                    "content/learning-paths/category/example/images/html.png": b"html",
                    "content/learning-paths/category/example/images/hugo.webp": b"hugo",
                }
            )
        )

        self.assertEqual(analysis.orphan_images, [])
        self.assertEqual(analysis.problems, [])
        self.assertEqual(analysis.referenced_images, 4)

    def test_malformed_reference_reserves_the_probable_image(self) -> None:
        malformed = (
            "![Device dialog#center](./create.webp \"Create dialog\""
            "duplicated text#center](./create.webp \"Create dialog\")\n"
        )
        analysis = orphan_images.analyze(
            snapshot(
                {
                    "content/learning-paths/category/example/guide.md": malformed,
                    "content/learning-paths/category/example/create.webp": b"image",
                }
            )
        )

        self.assertEqual(analysis.orphan_images, [])
        self.assertEqual([problem.kind for problem in analysis.problems], ["malformed_markdown"])

    def test_reports_case_mismatch_without_orphaning_the_image(self) -> None:
        analysis = orphan_images.analyze(
            snapshot(
                {
                    "content/learning-paths/category/example/guide.md": (
                        "![Architecture#center](images/Architecture.png)\n"
                    ),
                    "content/learning-paths/category/example/images/architecture.png": b"image",
                }
            )
        )

        self.assertEqual(analysis.orphan_images, [])
        self.assertEqual([problem.kind for problem in analysis.problems], ["case_mismatch"])

    def test_reports_missing_rendered_image_but_ignores_code_example(self) -> None:
        guide = """![Missing#center](missing.png)

`![Inline example](not-rendered.png)`

```html
<img src="generated-later.png">
```
"""
        analysis = orphan_images.analyze(
            snapshot({"content/learning-paths/category/example/guide.md": guide})
        )

        missing = [problem for problem in analysis.problems if problem.kind == "missing_image"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].target, "missing.png")

    def test_unique_orphan_needs_review_without_generated_site(self) -> None:
        image = "content/learning-paths/category/example/unused.png"
        analysis = orphan_images.analyze(snapshot({image: b"unused"}))

        self.assertEqual(analysis.orphan_images, [image])
        self.assertEqual(analysis.safe_delete_images, [])
        self.assertEqual(analysis.needs_review_images, [image])

    def test_exact_duplicate_orphan_is_safe_without_generated_site(self) -> None:
        source = "content/learning-paths/category/example/guide.md"
        used = "content/learning-paths/category/example/used.png"
        duplicate = "content/learning-paths/category/example/duplicate.png"
        analysis = orphan_images.analyze(
            snapshot(
                {
                    source: "![Used](used.png)\n",
                    used: b"same image",
                    duplicate: b"same image",
                }
            )
        )

        self.assertEqual(analysis.orphan_images, [duplicate])
        self.assertEqual(analysis.safe_delete_images, [duplicate])
        self.assertEqual(analysis.duplicate_orphans, {duplicate: (used,)})

    def test_rendered_site_evidence_marks_unique_orphan_safe(self) -> None:
        image = "content/learning-paths/category/example/unused.png"
        analysis = orphan_images.analyze(snapshot({image: b"unused"}), set())

        self.assertTrue(analysis.generated_site_checked)
        self.assertEqual(analysis.safe_delete_images, [image])
        self.assertEqual(analysis.needs_review_images, [])

    def test_unresolved_missing_reference_keeps_nearby_orphan_for_review(self) -> None:
        source = "content/learning-paths/category/example/guide.md"
        image = "content/learning-paths/category/example/other.png"
        analysis = orphan_images.analyze(
            snapshot({source: "![Missing](expected.png)\n", image: b"other"}),
            set(),
        )

        self.assertEqual(analysis.safe_delete_images, [])
        self.assertEqual(analysis.needs_review_images, [image])

    def test_repairable_missing_candidate_is_protected_until_fixed(self) -> None:
        source = "content/learning-paths/category/example/guide.md"
        image = "content/learning-paths/category/example/screenshot.webp"
        analysis = orphan_images.analyze(
            snapshot({source: "![Screenshot](screenshot.png)\n", image: b"screen"}),
            set(),
        )

        missing = [problem for problem in analysis.problems if problem.kind == "missing_image"]
        self.assertEqual(missing[0].replacement, image)
        self.assertEqual(analysis.safe_delete_images, [])
        self.assertEqual(analysis.needs_review_images, [image])

    def test_generated_site_reference_marks_asset_used(self) -> None:
        image = "content/learning-paths/category/example/rendered.png"
        absolute = "content/learning-paths/category/example/absolute.webp"
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            output = site / "learning-paths/category/example/index.html"
            output.parent.mkdir(parents=True)
            output.write_text(
                '<img src="rendered.png">'
                '<img src="https://learn.arm.com/learning-paths/category/example/absolute.webp">',
                encoding="utf-8",
            )

            generated = orphan_images.generated_site_references(site, {image, absolute})

        analysis = orphan_images.analyze(
            snapshot({image: b"rendered", absolute: b"absolute"}), generated
        )
        self.assertEqual(generated, {image, absolute})
        self.assertEqual(analysis.orphan_images, [])

    def test_empty_generated_site_cannot_upgrade_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                orphan_images.generated_site_references(Path(directory), set())

    def test_repository_text_reserves_an_exact_content_asset(self) -> None:
        image = "content/learning-paths/category/example/future.png"
        analysis = orphan_images.analyze(
            snapshot({"docs/images.md": f"Reserved: {image}\n", image: b"future"})
        )

        self.assertEqual(analysis.orphan_images, [])
        self.assertEqual(analysis.problems, [])

    def test_changed_since_reports_a_new_orphan_after_reference_removal(self) -> None:
        image = "content/learning-paths/category/example/used.png"
        source = "content/learning-paths/category/example/guide.md"
        baseline = orphan_images.analyze(
            snapshot({source: "![Used#center](used.png)\n", image: b"image"})
        )
        current = orphan_images.analyze(
            snapshot({source: "The image was removed.\n", image: b"image"})
        )

        problems = orphan_images.new_problems(current, baseline)
        self.assertEqual([(problem.kind, problem.path) for problem in problems], [("orphan", image)])

    def test_changed_since_reports_orphan_when_reference_file_is_deleted(self) -> None:
        image = "content/learning-paths/category/example/used.png"
        source = "content/learning-paths/category/example/guide.md"
        baseline = orphan_images.analyze(
            snapshot({source: "![Used](used.png)\n", image: b"image"})
        )
        current = orphan_images.analyze(snapshot({image: b"image"}))

        problems = orphan_images.new_problems(current, baseline)

        self.assertEqual(
            [(problem.kind, problem.path) for problem in problems],
            [("orphan", image)],
        )

    def test_changed_since_reports_missing_reference_when_image_is_deleted(self) -> None:
        image = "content/learning-paths/category/example/used.png"
        source = "content/learning-paths/category/example/guide.md"
        baseline = orphan_images.analyze(
            snapshot({source: "![Used](used.png)\n", image: b"image"})
        )
        current = orphan_images.analyze(snapshot({source: "![Used](used.png)\n"}))

        problems = orphan_images.new_problems(current, baseline)

        self.assertEqual(
            [(problem.kind, problem.path) for problem in problems],
            [("missing_image", source)],
        )

    def test_changed_since_ignores_a_preexisting_orphan(self) -> None:
        image = "content/learning-paths/category/example/unused.png"
        baseline = orphan_images.analyze(snapshot({image: b"image"}))
        current = orphan_images.analyze(snapshot({image: b"image"}))

        self.assertEqual(orphan_images.new_problems(current, baseline), [])

    def test_repairs_duplicated_markdown_corruption(self) -> None:
        malformed = (
            '![Device dialog#center](./create.webp "Create dialog"'
            'duplicated text#center](./create.webp "Create dialog")\n'
        )

        repaired = orphan_images.repair_duplicated_image_line(malformed)

        self.assertEqual(
            repaired,
            '![Device dialog#center](./create.webp "Create dialog")\n',
        )

    def test_applies_unambiguous_case_and_missing_reference_fixes(self) -> None:
        source = "content/learning-paths/category/example/guide.md"
        guide = (
            "![Architecture](images/Architecture.png)\n"
            "![Title screen](/images/title-screen.jpg)\n"
        )
        files = {
            source: guide,
            "content/learning-paths/category/example/images/architecture.png": b"diagram",
            "content/learning-paths/category/example/images/title-screen.jpg": b"screen",
        }
        analysis = orphan_images.analyze(snapshot(files))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / source
            source_path.parent.mkdir(parents=True)
            source_path.write_text(guide, encoding="utf-8")

            changes = orphan_images.apply_safe_reference_fixes(root, analysis)

            self.assertEqual(len(changes), 2)
            self.assertEqual(
                source_path.read_text(encoding="utf-8"),
                "![Architecture](images/architecture.png)\n"
                "![Title screen](./images/title-screen.jpg)\n",
            )

    def test_does_not_guess_between_ambiguous_missing_assets(self) -> None:
        source = "content/learning-paths/category/example/guide.md"
        analysis = orphan_images.analyze(
            snapshot(
                {
                    source: "![Diagram](missing/diagram.png)\n",
                    "content/learning-paths/category/example/one/diagram.png": b"one",
                    "content/learning-paths/category/example/two/diagram.png": b"two",
                }
            )
        )

        missing = [problem for problem in analysis.problems if problem.kind == "missing_image"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].replacement, "")

    def test_safe_deletion_preserves_case_colliding_worktree_file(self) -> None:
        regular = "content/learning-paths/category/example/unused.png"
        lower = "content/learning-paths/category/example/image.png"
        upper = "content/learning-paths/category/example/Image.png"
        with mock.patch.object(orphan_images.subprocess, "check_call") as check_call:
            changes = orphan_images.delete_safe_images(
                Path("/repo"),
                [regular, lower],
                [regular, lower, upper],
            )

        self.assertEqual(
            check_call.call_args_list,
            [
                mock.call(["git", "-C", "/repo", "rm", "-q", "--", regular]),
                mock.call(
                    ["git", "-C", "/repo", "rm", "--cached", "-q", "--", lower]
                ),
            ],
        )
        self.assertEqual(
            [(change.kind, change.path) for change in changes],
            [
                ("deleted_safe_orphan", regular),
                ("removed_duplicate_index_entry", lower),
            ],
        )


if __name__ == "__main__":
    unittest.main()
