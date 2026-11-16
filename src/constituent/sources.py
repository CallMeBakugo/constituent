"""Read only public congressional records. No profile data enters this module."""

import io
import re
import zipfile
from html.parser import HTMLParser
from collections import defaultdict
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

GPO = "https://www.govinfo.gov/bulkdata/BILLSTATUS"
HOUSE_XML = "https://clerk.house.gov/xml/lists/MemberData.xml"
HOUSE_SITES = "https://www.house.gov/representatives"
SENATE_XML = "https://www.senate.gov/general/contact_information/senators_cfm.xml"
HOUSE_LOOKUP = "https://www.house.gov/representatives/find-your-representative"
FISC_OPINIONS = "https://www.fisc.uscourts.gov/public-filings"


def fetch(url, validators=None):
    headers = {"User-Agent": "Constituent/0.2 (public congressional records)"}
    headers.update(validators or {})
    try:
        with urlopen(Request(url, headers=headers), timeout=45) as response:
            data = response.read(100 * 1024 * 1024 + 1)
            if len(data) > 100 * 1024 * 1024:
                raise ValueError("Official download exceeded the supported size.")
            validators = {
                request: response.headers[header]
                for header, request in (
                    ("ETag", "If-None-Match"),
                    ("Last-Modified", "If-Modified-Since"),
                )
                if response.headers.get(header)
            }
            return data, validators
    except HTTPError as error:
        if error.code == 304:
            return None, validators
        raise


def field(node, path):
    return (node.findtext(path) or "").strip()


def chamber_url(value, chamber):
    if not value.startswith(("http://", "https://")):
        return ""
    host = urlsplit(value).hostname or ""
    domain = f"{chamber.lower()}.gov"
    if host == domain or host.endswith(f".{domain}"):
        return value.replace("http://", "https://", 1)
    return ""


class PlainText(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "li", "br", "ul", "ol"}:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n\n".join(filter(None, lines))


def lifecycle(actions, laws, kind):
    """Recognize explicit milestones and leave ambiguous procedural votes alone."""
    if laws:
        return "Enacted"
    status = "Proposed"
    house_passed = senate_passed = False
    for action in reversed(actions):
        text = action["text"].lower()
        code = action["code"]
        if code in {"E30000", "E40000", "36000"} or text.startswith(
            ("became public law", "became private law", "signed by president")
        ):
            return "Enacted"
        if text.startswith(("vetoed by president", "pocket vetoed", "on passage failed",
                            "failed of passage", "on passage of the bill failed")):
            status = "Failed"
        elif code == "8000" or text.startswith(("passed house", "on passage passed")):
            house_passed = True
            status = "Passed"
        elif code == "17000" or text.startswith("passed senate"):
            senate_passed = True
            status = "Passed"
        elif code in {"E20000", "28000"} or text.startswith(("presented to president", "cleared for white house")):
            status = "Passed"
        elif not (house_passed and senate_passed) and status != "Failed":
            other_chamber = (kind == "HR" and house_passed) or (kind == "S" and senate_passed)
            if not other_chamber or code in {"H14000", "H11100", "2000", "11000", "H12410"} or text.startswith(
                ("received in the", "read twice and referred", "read twice and placed")
            ):
                if code in {"H12410", "H30000", "5000", "14000"} or text.startswith(
                    ("placed on", "reported by", "committee on ", "considered by", "considered under")
                ) and any(word in text for word in ("calendar", "reported by", "considered ")):
                    status = "On Floor"
                elif code in {"H11100", "H11200", "2000", "11000"} or "referred to the committee" in text:
                    status = "In Committee"
    return status



def vote_page(url):
    house = re.fullmatch(r"https?://clerk\.house\.gov/evs/?(\d{4})/roll(\d+)\.xml", url)
    if house:
        return f"https://clerk.house.gov/Votes/{house[1]}{int(house[2])}"
    senate = re.fullmatch(r"https?://www\.senate\.gov/legislative/LIS/roll_call_votes/(vote\d+/vote_\d+_\d+_\d+)\.xml", url)
    if senate:
        return f"https://www.senate.gov/legislative/LIS/roll_call_votes/{senate[1]}.htm"
    return url

def bill_from_xml(data):
    node = ET.fromstring(data).find("bill")
    if node is None:
        raise ValueError("Missing bill status record.")
    actions = []
    for item in node.findall("actions/item"):
        date, text = field(item, "actionDate"), field(item, "text")
        if date and text:
            links = [
                (field(link, "name"), field(link, "url"))
                for link in item.findall("links/link")
            ]
            for vote in item.findall("recordedVotes/recordedVote"):
                url = field(vote, "url")
                number = field(vote, "rollNumber")
                links.append((f"Roll call {number}", url))
            actions.append({
                "date": date, "text": text, "code": field(item, "actionCode"),
                "links": list(dict.fromkeys((name, vote_page(url)) for name, url in links)),
            })
    actions.sort(key=lambda action: action["date"], reverse=True)
    latest = field(node, "latestAction/text")
    date = field(node, "latestAction/actionDate") or field(node, "introducedDate")
    if latest and not any(action["date"] == date and action["text"] == latest for action in actions):
        actions.insert(0, {"date": date, "text": latest, "code": "", "links": []})
    summaries = []
    for item in node.findall("summaries/summary") + node.findall("summaries/item"):
        summary = PlainText(field(item, "text")).text()
        if summary:
            summaries.append((field(item, "actionDate"), summary))
    sponsors = [
        {"id": field(item, "bioguideId"), "name": field(item, "fullName")}
        for item in node.findall("sponsors/item")
    ]
    cosponsors = [
        {"id": field(item, "bioguideId"), "name": field(item, "fullName"),
         "withdrawn": field(item, "sponsorshipWithdrawnDate")}
        for item in node.findall("cosponsors/item")
    ]
    congress, number = int(field(node, "congress")), int(field(node, "number"))
    kind = field(node, "type").upper()
    label = {"HR": "H.R.", "S": "S."}[kind]
    laws = [field(item, "number") for item in node.findall("laws/item")]
    return {
        "key": f"{congress}-{kind.lower()}-{number}", "congress": congress,
        "bill_id": f"{label} {number}", "number": number, "kind": kind,
        "title": field(node, "title"),
        "titles": [field(item, "title") for item in node.findall("titles/item")],
        "date": date, "latest": latest, "status": lifecycle(actions, laws, kind),
        "source": field(node, "legislationUrl"),
        "updated": field(node, "updateDate"),
        "summary": max(summaries, default=("", ""), key=lambda item: item[0])[1],
        "committees": list(dict.fromkeys(field(item, "name") for item in node.findall("committees/item"))),
        "subjects": [field(item, "name") for item in node.findall("subjects/legislativeSubjects/item")],
        "sponsors": sponsors, "cosponsors": cosponsors, "actions": actions,
    }


def bills_from_archive(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = [
            info for info in archive.infolist()
            if re.fullmatch(r"BILLSTATUS-\d+(?:hr|s)\d+\.xml", info.filename, re.I)
        ]
        if not files or sum(info.file_size for info in files) > 900 * 1024 * 1024:
            raise ValueError("Unexpected GovInfo archive contents.")
        # Parse the full archive before replacing any cached records.
        return [bill_from_xml(archive.read(info)) for info in files]


class HouseSites(HTMLParser):
    def __init__(self, data):
        super().__init__(convert_charrefs=True)
        self.sites = {}
        self.phone_sites = defaultdict(set)
        self.row_text = None
        self.row_site = ""
        self.url = ""
        self.name = []
        self.feed(data.decode("utf-8", errors="replace"))

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row_text = []
            self.row_site = ""
        if tag == "a":
            self.url = chamber_url(dict(attrs).get("href", ""), "House")
            self.name = []

    def handle_data(self, text):
        if self.url:
            self.name.append(text)
        if self.row_text is not None:
            self.row_text.append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.url:
            self.sites[" ".join("".join(self.name).split()).casefold()] = self.url
            self.row_site = self.url
            self.url = ""
        if tag == "tr" and self.row_text is not None:
            phone = re.search(r"\(202\) \d{3}-\d{4}", " ".join(self.row_text))
            if phone and self.row_site:
                self.phone_sites[phone.group()].add(self.row_site)
            self.row_text = None

    def lookup(self, name, phone):
        sites = self.phone_sites[phone]
        if len(sites) == 1:
            return next(iter(sites))
        return self.sites.get(name.casefold(), "")


def house_members(data, page):
    root = ET.fromstring(data)
    sites = HouseSites(page)
    committees = {
        node.get("comcode"): field(node, "committee-fullname")
        for node in root.findall("committees/committee")
    }
    results = []
    for entry in root.findall("members/member"):
        node = entry.find("member-info")
        member_id = field(node, "bioguideID")
        district = field(entry, "statedistrict")
        if not member_id or not re.fullmatch(r"[A-Z]{2}\d{2}", district):
            continue
        building = {"CHOB": "Cannon", "LHOB": "Longworth", "RHOB": "Rayburn"}.get(
            field(node, "office-building"), field(node, "office-building")
        )
        room = field(node, "office-room")
        address = f"{room} {building} House Office Building, Washington, DC {field(node, 'office-zip')}" if room else ""
        phone = field(node, "phone")
        state = {"AQ": "AS"}.get(district[:2], district[:2])
        results.append({
            "id": member_id, "name": field(node, "official-name"),
            "party": field(node, "party"), "state": state, "district": district[2:],
            "chamber": "House", "phone": phone, "address": address,
            "site": sites.lookup(field(node, "namelist"), phone),
            "form": "", "email": "", "term": f"Sworn in {field(node, 'sworn-date')}",
            "committees": [
                committees[item.get("comcode")]
                for item in entry.findall("committee-assignments/committee")
                if item.get("comcode") in committees
            ],
        })
    if len(results) < 400:
        raise ValueError("Incomplete House directory.")
    return results


def senate_members(data):
    results = []
    for node in ET.fromstring(data).findall("member"):
        member_id = field(node, "bioguide_id")
        if not member_id:
            continue
        contact = field(node, "email").removeprefix("mailto:")
        results.append({
            "id": member_id, "name": f"{field(node, 'first_name')} {field(node, 'last_name')}",
            "party": field(node, "party"), "state": field(node, "state"),
            "district": "", "chamber": "Senate", "phone": field(node, "phone"),
            "address": field(node, "address"),
            "site": chamber_url(field(node, "website"), "Senate"),
            "form": chamber_url(contact, "Senate"),
            "email": contact if re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.senate\.gov", contact) else "",
            "term": field(node, "class"), "committees": [],
        })
    if len(results) < 90:
        raise ValueError("Incomplete Senate directory.")
    return results


class CourtFilings(HTMLParser):
    """Extract the dates and title links from the court's first index page."""

    def __init__(self, data):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.row = None
        self.cell = ""
        self.title = []
        self.feed(data.decode("utf-8", errors="replace"))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = {}
            self.title = []
        if self.row is None:
            return
        if tag == "td":
            fields = {
                "views-field-field-filed-date": "filed",
                "views-field-field-post-date": "posted",
                "views-field-title": "title",
            }
            self.cell = next((fields[c] for c in attrs.get("class", "").split() if c in fields), "")
        elif tag == "span" and self.cell in {"filed", "posted"} and attrs.get("property") == "dc:date":
            self.row[self.cell] = attrs.get("content", "")[:10]
        elif tag == "a" and self.cell == "title":
            href = attrs.get("href", "")
            if href.startswith("/public-filings/"):
                self.row["url"] = f"https://www.fisc.uscourts.gov{href}"

    def handle_data(self, text):
        if self.cell == "title":
            self.title.append(text)

    def handle_endtag(self, tag):
        if tag == "td":
            self.cell = ""
        if tag == "tr" and self.row is not None:
            if self.row.get("url") and self.title:
                self.row["title"] = " ".join("".join(self.title).split())
                self.items.append(self.row)
            self.row = None


def court_filings(data):
    records = CourtFilings(data).items
    if not records:
        raise ValueError("The court filings index contained no records.")
    return records
