"""Check local file targets in repository-level Markdown documentation."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]


def local_targets(markdown):
    # Exclude examples; validate inline destinations and reference definitions.
    lines = []
    fence = None
    for line in markdown.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker[1]
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    text = re.sub(r"(`+).*?\1", "", "\n".join(lines))
    destinations = re.findall(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)", text)
    destinations += re.findall(r"(?m)^\s{0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", text)
    for destination in destinations:
        url = urlsplit(destination.strip("<>"))
        if not url.scheme and not url.netloc and url.path:
            yield unquote(url.path)


class DocumentLinkTests(unittest.TestCase):
    def test_repository_document_targets_exist(self):
        documents = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").rglob("*.md"))
        for document in documents:
            for target in local_targets(document.read_text(encoding="utf-8")):
                with self.subTest(document=str(document.relative_to(ROOT)), target=target):
                    self.assertTrue((document.parent / target).exists(), "Broken local Markdown link")

    def test_extracts_local_files_but_not_examples_or_remote_links(self):
        sample = '''
[release](docs/release-notes-template.md#usage)
![image](docs/image.png)
[checklist]: docs/release-checklist.md "Release checklist"
[encoded](docs/space%20name.md)
[spaces](<docs/space name.md>)
[web](https://example.com/missing.md)
[email](mailto:test@example.invalid)
[section](#usage)
`[inline example](missing-inline.md)`
```md
[example](missing-example.md)
```
'''
        self.assertEqual(list(local_targets(sample)), [
            "docs/release-notes-template.md", "docs/image.png", "docs/space name.md",
            "docs/space name.md", "docs/release-checklist.md",
        ])


if __name__ == "__main__":
    unittest.main()
