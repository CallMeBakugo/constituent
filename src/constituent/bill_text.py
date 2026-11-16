"""Published bill text from GovInfo's session and chamber archives."""

import io
import re
import zipfile
from hashlib import sha256
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

GPO_BILL_TEXT = "https://www.govinfo.gov/bulkdata/BILLS"
DOCUMENT = re.compile(r"(BILLS-(\d+)(hr|s)(\d+)[a-z0-9]+)\.xml")


def archive_url(congress, session, kind):
    return f"{GPO_BILL_TEXT}/{congress}/{session}/{kind}/BILLS-{congress}-{session}-{kind}.zip"


def document_url(package):
    return f"https://www.govinfo.gov/app/details/{package}"


def document_text(data):
    root = ET.fromstring(data)
    # XML children include bill forms, legislative bodies and, when applicable,
    # engrossed amendment bodies. Catalog metadata would add non-bill matches.
    return " ".join(
        part.strip()
        for child in root
        if child.tag.rsplit("}", 1)[-1] != "metadata"
        for part in child.itertext()
        if part.strip()
    )


def archive_documents(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        documents = []
        for info in archive.infolist():
            if match := DOCUMENT.fullmatch(PurePosixPath(info.filename).name):
                package, congress, chamber, number = match.groups()
                documents.append((package, f"{congress}-{chamber}-{number}", info))
        if not documents or sum(info.file_size for _, _, info in documents) > 900 * 1024 * 1024:
            raise ValueError("Unexpected GovInfo bill text archive contents.")
        for package, key, info in documents:
            raw = archive.read(info)
            yield package, key, sha256(raw).digest(), raw
