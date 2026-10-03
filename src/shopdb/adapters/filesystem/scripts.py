from shopdb.settings import ROOT

POST_LOAD_DIR = ROOT / "db" / "post_load"


def post_load_files(only=None):
    return [p for p in sorted(POST_LOAD_DIR.glob("*.sql")) if not only or p.name.startswith(only)]


def scripts(only=None):
    return [(p.name, p.read_text(encoding="utf-8")) for p in post_load_files(only)]
