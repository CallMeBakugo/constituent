"""Resolve contact links and representative votes from official office and chamber sites."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

from .legislation import action_kind, EVENT_LABELS
from .sources import chamber_url, fetch, field


class Contacts(HTMLParser):
    def __init__(self, body, site):
        super().__init__(convert_charrefs=True)
        self.site = site
        self.links = []
        self.anchor = ""
        self.parts = []
        self.feed(body.decode("utf-8", errors="replace"))

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchor = dict(attrs).get("href") or ""
            self.parts = []

    def handle_data(self, text):
        if self.anchor:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag != "a" or not self.anchor:
            return
        url = urljoin(self.site, self.anchor)
        parsed = urlsplit(url)
        name = " ".join("".join(self.parts).casefold().split())
        path = parsed.path.rstrip("/").lower()
        if (parsed.scheme == "https"
            and (parsed.hostname or "").removeprefix("www.") == urlsplit(self.site).hostname.removeprefix("www.")
            and url != self.site
            and not any(word in path for word in ("casework", "newsletter", "district", "press", "privacy"))):
            direct_paths = ("/contact/email-me", "/contact/email", "/email-me", "/contact/send-me-an-email")
            direct_names = ("email me", "send me an email", "write to me", "email the congressman",
                            "email the congresswoman", "email the representative")
            if path in direct_paths or name in direct_names:
                self.links.append((0, url))
            elif path in ("/contact", "/contact-us", "/contact-me") or name in ("contact", "contact me", "contact us"):
                self.links.append((1, url))
        self.anchor = ""


def contact_link(body, site):
    return min(Contacts(body, site).links, default=(2, ""))[1]


def official_contact(store, office):
    # Only published office URLs are fetched. No constituent data enters this module.
    form = office.get("form", "")
    site = chamber_url(office.get("site", ""), office["chamber"])
    if form and form.rstrip("/") != site.rstrip("/"):
        return form
    if not site:
        return ""
    key = "contact:" + site
    cached, checked = store.cached_lookup(key)
    if checked and datetime.now().astimezone() - datetime.fromisoformat(checked) < timedelta(days=7):
        return cached
    try:
        data, _ = fetch(site, timeout=8)
    except (OSError, ValueError):
        return cached or ""
    link = contact_link(data, site)
    store.save_lookup(key, link)
    return link


def roll_xml(url):
    if match := re.fullmatch(r"https://clerk\.house\.gov/Votes/(\d{4})(\d+)", url):
        return f"https://clerk.house.gov/evs/{match[1]}/roll{int(match[2]):03d}.xml", "House"
    if match := re.fullmatch(
        r"https://www\.senate\.gov/legislative/LIS/roll_call_votes/(vote\d+/vote_\d+_\d+_\d+)\.htm", url
    ):
        return f"https://www.senate.gov/legislative/LIS/roll_call_votes/{match[1]}.xml", "Senate"
    return None


def vote_records(data, chamber):
    root = ET.fromstring(data)
    if chamber == "House":
        return [
            {"id": item.find("legislator").get("name-id", ""), "vote": field(item, "vote")}
            for item in root.findall("vote-data/recorded-vote") if item.find("legislator") is not None
        ]
    return [
        {"state": field(item, "state"), "last_name": field(item, "last_name"),
         "first_name": field(item, "first_name"), "vote": field(item, "vote_cast")}
        for item in root.findall("members/member")
    ]


def office_vote(office, records):
    if office["chamber"] == "House":
        return next((record["vote"] for record in records if record["id"] == office["id"]), "")
    surname = office.get("last_name") or office["name"].split()[-1]
    matches = [r for r in records if r["state"] == office["state"] and r["last_name"].casefold() == surname.casefold()]
    if len(matches) > 1:
        first = office["name"].split()[0].casefold()
        matches = [r for r in matches if r["first_name"].casefold().split()[:1] == [first]]
    return matches[0]["vote"] if len(matches) == 1 else ""


def bill_votes(store, bill, offices):
    roll_calls = {}
    for action in bill["actions"]:
        for name, url in action.get("links", ()):
            source = roll_xml(url)
            if source and any(office["chamber"] == source[1] for office in offices):
                roll_calls.setdefault(url, (source, action, EVENT_LABELS.get(action_kind(action), "Roll call")))

    def load(item):
        url, ((xml, chamber), action, label) = item
        records, _ = store.cached_lookup("vote:" + xml)
        if records is None:
            try:
                data, _ = fetch(xml, timeout=8)
                records = vote_records(data, chamber)
                if records:
                    store.save_lookup("vote:" + xml, records)
            except (OSError, ValueError, ET.ParseError):
                return []
        result = []
        for office in offices:
            if chamber == office["chamber"] and (vote := office_vote(office, records)):
                result.append((office["id"], vote, action["date"], label, url))
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [entry for results in pool.map(load, roll_calls.items()) for entry in results]
