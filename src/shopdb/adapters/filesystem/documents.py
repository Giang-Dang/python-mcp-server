from pathlib import Path


class DocumentWriter:
    def __init__(self, directory: Path):
        self.directory = directory

    def __call__(self, name: str, text: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path
