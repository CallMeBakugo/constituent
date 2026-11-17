"""Interpret public bill actions without treating procedural votes as passage."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Stage:
    status: str
    label: str
    chamber: str


def action_chamber(action, fallback):
    text = action["text"].casefold()
    code = action.get("code", "")
    if code in {"8000", "9000", "2000", "5000"} or code.startswith("H"):
        return "House"
    if code in {"17000", "18000", "11000", "14000"}:
        return "Senate"
    for chamber in ("House", "Senate"):
        lower = chamber.lower()
        if re.search(rf"\b(?:in|by|to) (?:the )?{lower}\b", text):
            return chamber
    if "received in the senate" in text or "message on house action received" in text:
        return "Senate"
    source = action.get("chamber", "")
    return source if source in {"House", "Senate"} else fallback


def action_kind(action):
    text, code = action["text"].casefold(), action.get("code", "")
    if code in {"E30000", "E40000", "36000"} or text.startswith(
        ("became public law", "became private law", "signed by president")
    ):
        return "law"
    if code in {"E20000", "28000"} or text.startswith(("presented to president", "cleared for white house")):
        return "president"
    if "vetoed by president" in text or "pocket vetoed" in text:
        return "veto"
    if text.startswith("on motion to suspend the rules and pass"):
        if "failed by" in text:
            return "failed"
        if "agreed to by" in text:
            return "passed"
    if code in {"9000", "18000"} or text.startswith(
        ("on passage failed", "failed of passage", "on passage of the bill failed")
    ):
        return "failed"
    if code in {"8000", "17000"} or text.startswith(
        ("passed house", "passed senate", "on passage passed", "passed/agreed to in ")
    ):
        return "passed"
    if (text.startswith(("motion to proceed", "cloture")) and
            (re.search(r"\b(?:rejected|failed|not agreed to)\b", text))):
        return "blocked"
    if ("legislative calendar" in text and "read the first time" not in text) or code in {"H12410", "H12411", "H12420"}:
        return "calendar"
    if code in {"5000", "14000", "H12200", "H12300"} or text.startswith("reported by"):
        return "reported"
    if re.search(r"\b(?:ordered to be reported|committee consideration and mark-up|forwarded by subcommittee)\b", text):
        return "committee_vote"
    if code in {"2000", "11000", "H11100", "H11200"} or re.search(
        r"\breferred to (?:the )?(?:(?:senate|house|select|standing|joint|special) )?committee\b", text
    ):
        return "referral"
    if code in {"H14000", "H15000"} or text.startswith(("received in the", "message on house action received", "held at the desk")):
        return "received"
    if code == "H30000" or text.startswith(("considered by", "considered under", "considered as unfinished")):
        return "floor"
    return ""


EVENT_LABELS = {
    "law": "Enactment", "president": "Presented to President", "veto": "Veto",
    "failed": "Failed passage vote", "passed": "Passage", "blocked": "Procedural defeat",
    "calendar": "Calendar placement", "reported": "Committee report",
    "committee_vote": "Committee action", "referral": "Referral", "received": "Chamber receipt",
    "floor": "Floor consideration",
}


def bill_stage(actions, kind, enacted=False):
    chamber = "House" if kind == "HR" else "Senate"
    if enacted:
        return Stage("Enacted", "Enacted", "")
    stage = Stage("Proposed", f"Introduced in {chamber}", chamber)
    passed = set()
    for action in reversed(actions):
        event = action_kind(action)
        if not event:
            continue
        chamber = action_chamber(action, chamber)
        if event == "law":
            return Stage("Enacted", "Enacted", "")
        if event == "president":
            stage = Stage("Passed", "Presented to President", "")
        elif event == "veto":
            stage = Stage("Failed", "Vetoed", "")
        elif event == "passed":
            text = action["text"].lower()
            amended = ("with amendment" in text or "with an amendment" in text
                       or "with a substitute" in text or "as amended" in text)
            # A chamber adopting a different version requires the other to agree again.
            if amended:
                passed.clear()
            passed.add(chamber)
            text = "Passed both chambers" if len(passed) == 2 else f"Passed {chamber}"
            stage = Stage("Passed", text, "" if len(passed) == 2 else chamber)
        elif event == "failed":
            stage = Stage("Failed", f"Failed {chamber} passage vote", chamber)
        elif event == "blocked":
            other = next(iter(passed - {chamber}), "")
            label = f"{chamber} motion blocked"
            stage = Stage("On Floor", f"Passed {other} · {label}" if other else label, chamber)
        elif len(passed) < 2 and stage.status != "Enacted":
            labels = {
                "calendar": ("On Floor", f"On {chamber} calendar"),
                "reported": ("On Floor", f"Reported to {chamber}"),
                "floor": ("On Floor", f"On {chamber} floor"),
                "committee_vote": ("In Committee", f"In {chamber} committee"),
                "referral": ("In Committee", f"In {chamber} committee"),
                "received": (stage.status if chamber in passed else "On Floor", f"At {chamber} desk"),
            }
            if event in labels:
                status, text = labels[event]
                other = next(iter(passed - {chamber}), "")
                if other:
                    text = f"Passed {other} · {text}"
                stage = Stage(status, text, chamber)
    return stage
