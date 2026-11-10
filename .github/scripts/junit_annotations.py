"""Turn JUnit XML failures into GitHub annotations (visible on the run page without a sign-in)."""

import sys
import xml.etree.ElementTree as ET  # noqa: S405 (trusted CI artefact)


def esc(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main(path: str) -> None:
    try:
        root = ET.parse(path).getroot()  # noqa: S314
    except (OSError, ET.ParseError):
        print(f"::warning::no junit report at {path}")
        return
    shown = 0
    for case in root.iter("testcase"):
        for tag in ("failure", "error"):
            node = case.find(tag)
            if node is None or shown >= 10:
                continue
            shown += 1
            name = f"{case.get('classname')}::{case.get('name')}"
            detail = (node.get("message") or "") + "\n" + (node.text or "")[-1500:]
            print(f"::error title={esc(name)}::{esc(detail)}")


if __name__ == "__main__":
    main(sys.argv[1])
