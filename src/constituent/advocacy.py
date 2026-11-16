"""Render plain-text letters and RFC 6068 mailto URLs."""

import re
from urllib.parse import quote, urlencode

BODY = """Dear {{official_title}} {{official_name}},

I am writing as your constituent to ask you to {{stance}} {{bill_id}}, {{bill_title}}, which is currently listed as {{bill_stage}}.

Please consider my position when this measure or a related proposal comes before your office. I would appreciate hearing where you stand and how you plan to act.

Respectfully,
{{user_name}}
{{user_address}}
"""
TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def ensure_templates(config):
    directory = config / "templates"
    directory.mkdir(exist_ok=True, mode=0o700)
    for stance in ("support", "oppose"):
        try:
            with (directory / f"{stance}.txt").open("x", encoding="utf-8") as handle:
                handle.write(BODY)
        except FileExistsError:
            pass
    return directory


def letter(directory, bill, office, profile, stance):
    if stance not in {"support", "oppose"}:
        raise ValueError("Unknown stance.")
    title = "Senator" if office["chamber"] == "Senate" else "Representative"
    fields = {
        "official_name": office["name"], "official_title": title,
        "bill_id": bill["bill_id"], "bill_title": bill["title"],
        "bill_stage": bill["status"], "stance": stance,
        "user_name": profile["name"], "user_address": profile["address"],
    }
    template = (directory / f"{stance}.txt").read_text(encoding="utf-8")
    unknown = set(TOKEN.findall(template)) - fields.keys()
    if unknown:
        raise ValueError(f"Unknown template fields: {', '.join(sorted(unknown))}")
    return (
        f"[{stance.title()}] {bill['bill_id']} — {title} {office['name']}",
        TOKEN.sub(lambda match: fields[match[1]], template).strip(),
    )


def mailto(email, subject, body):
    query = urlencode({"subject": subject, "body": "\r\n".join(body.splitlines())}, quote_via=quote)
    return f"mailto:{quote(email, safe='@')}?{query}"
