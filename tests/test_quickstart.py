"""The standalone guide keeps its image slot and in-page navigation usable."""

from html.parser import HTMLParser
from pathlib import Path


class GuideParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        properties = {key: value or "" for key, value in attrs}
        if properties.get("id"):
            self.ids.add(properties["id"])
        if tag == "a":
            self.links.append(properties.get("href", ""))
        if tag == "img":
            self.images.append(properties)


def test_quickstart_uses_root_source_ui_image_with_visible_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    guide = (root / "QUICKSTART.html").read_text(encoding="utf-8")
    parser = GuideParser()
    parser.feed(guide)

    assert guide.lstrip().startswith("<!doctype html>")
    assert {"preview", "setup", "features", "faq", "ui-placeholder"} <= parser.ids
    assert {"#preview", "#setup", "#features", "#faq"} <= set(parser.links)
    assert "README.md" in parser.links
    assert (root / "README.md").is_file()
    assert any(image.get("src") == "source/UI.PNG" for image in parser.images)
    assert "source\\UI.PNG" in guide
    assert "image.naturalWidth > 0" in guide
    assert "placeholder.hidden = available" in guide
