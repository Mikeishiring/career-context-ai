"""Review common implied links in English questions against the cited source text."""
import re


DAY = r"(?:mon|tues|wednes|thurs|fri|satur|sun)day"
IGNORED = set("i a an the on in at to with for of and my your you their our what where did do does was were is are when how from that together someone they them one look like".split())


def words(text):
    return {re.sub(r"(?:ing|ed|s)$", "", w).removesuffix("e") for w in re.findall(r"[a-z]+", text.lower()) if w not in IGNORED}


def statements(sources):
    """Keep evidence local. Two facts in different sentences cannot prove a link."""
    return [clause.strip().lower() for source in sources
            for clause in re.split(r"[.!?;\n]+|,\s*(?:but|whereas)\s+|\s+(?:but|whereas)\s+", source)
            if clause.strip() and not re.search(r"\b(?:never|not|no|if|might|maybe|would|could have)\b|n['’]t\b", clause, re.I)]


def related(focus, line):
    terms = words(focus)
    return len(terms & words(line)) >= min(2, len(terms)) if terms else False


def dated_activity(day, activity, lines):
    date = re.compile(r"\b" + day.lower().rstrip("s") + r"s?\b")
    # Coordinated independent clauses may put the date on a different action.
    objects = re.findall(r"\b(?:a|an|the) ([a-z]+(?: [a-z]+)?)(?=\s+(?:together|with|look|on)\b|$)", activity.lower())
    for line in lines:
        for part in re.split(r"\band (?=i |we |they |he |she )", line):
            if not date.search(part):
                continue
            first_verb = activity.lower().removeprefix("i ").split()[0]
            # With a named action, the schedule of a colleague doing that action
            # cannot establish the candidate's schedule.
            if first_verb not in ("what", "where", "why", "how"):
                if not re.search(r"\b(?:i|we) " + re.escape(first_verb) + r"\b", part) and not part.startswith(first_verb + " "):
                    continue
            if related(activity, part) or any(re.search(r"\b" + obj + r"\b", part) for obj in objects):
                return True
    return False


def reviewed_account(account, lines, panel_fallback):
    changes = {}
    questions = [review(q, lines, panel_fallback)[0] for q in account["questions"]]
    if questions != account["questions"]:
        changes["questions"] = list(dict.fromkeys(questions))
    # A prepared account can itself have joined an action to a nearby date.
    # Narrow only when the cited text independently contains both details.
    for field in ("contribution", "summary"):
        text = account[field]
        match = re.fullmatch(rf"(I [^.!?;]+?) on ({DAY}s?)([.]?)", text, re.I)
        if (match and any(re.search(r"\b" + match[2].lower().rstrip("s") + r"s?\b", line) for line in lines)
                and any(related(match[1], line) for line in lines)
                and not dated_activity(match[2], match[1], lines)):
            changes[field] = match[1] + match[3]
    return changes


def review(question, lines, panel_fallback):
    """Return a replacement and its reason, or preserve the original wording."""
    q = question.strip().rstrip("?")
    recurrence = re.search(r"\bon the next ([\w -]{2,60})$", q, re.I)
    if recurrence and not any(re.search(r"\b(?:next|another|following|second) " + re.escape(recurrence[1].lower()) + r"\b", s)
                              and not re.search(r"\b(?:missed|cancelled|canceled|skipped)\b", s) for s in lines):
        return f"Was there another {recurrence[1]}?", "Unconfirmed repeat event"

    # Keep the useful part of the question when its date belongs to another fact.
    joined = re.fullmatch(rf"Where were you (?:working|covering|helping)(?: on)? ({DAY}s?) when you (.+)", q, re.I)
    if joined and not dated_activity(joined[1], joined[2], lines):
        return f"Where were you when you {joined[2]}?", "Unconfirmed timing"
    dated = re.fullmatch(rf"((?:what|where|how|why)\b.+?) on (?:a typical |a |the )?({DAY}s?)", q, re.I)
    if dated and not dated_activity(dated[2], dated[1], lines):
        return dated[1] + "?", "Unconfirmed timing"

    # A person receiving or seeing an object is a separate event from displaying it.
    seeing = re.fullmatch(r"What (?:exactly )?did ((?:a|an|the) [\w-]+) see on (the [\w -]+?)(?: when (.+))?", q, re.I)
    if seeing:
        actor = re.escape(seeing[1].split()[-1].lower())
        obj = re.escape(seeing[2].lower().removeprefix("the "))
        if not any(re.search(rf"\b{actor}s?\s+(?:saw|read|looked at|noticed)\b[^,;.!?]*\b{obj}\b", s)
                   and (not seeing[3] or related(seeing[3], s)) for s in lines):
            return f"Did {seeing[1]} see {seeing[2]}?", "Unconfirmed observation"

    boundary = re.fullmatch(r"Where did your work (.+?) end and (.+?)[’']s work (on .+?) begin", q, re.I)
    if boundary:
        other = re.escape(boundary[2].lower().removeprefix("the "))
        if not any(re.search(rf"\b{other} (?:then )?took over\b", s)
                   and related(boundary[3], s) and re.search(r"\b(?:from me|when i finished|after i finished)\b", s) for s in lines):
            return f"Did you work {boundary[3]} too?", "Unconfirmed handoff"

    solo = re.search(r"^Which part of (.+?) did (.+?) (.+?) (?:for (?:himself|herself|themselves)|on (?:his|her|their) own|independently)$", q, re.I)
    if solo:
        actor = re.escape(solo[2].lower().removeprefix("the "))
        if not any(re.search(rf"\b{actor}\b", s) and related(solo[1], s)
                   and re.search(r"\b(?:alone|independently|on (?:his|her|their) own|by (?:himself|herself|themselves))\b", s) for s in lines):
            return panel_fallback, "Unconfirmed independent action"

    exclusive = re.fullmatch(r"(What did .+?),? and what could you only (?:find out|learn|test|check) (.+)", q, re.I)
    if exclusive and not any(re.search(r"\bonly (?:find out|learn|test|check|measure|assess)\b", s)
                             and exclusive[2].lower() in s for s in lines):
        return re.sub(r"\b(?:those|these)\b", "the", exclusive[1], count=1, flags=re.I) + "?", "Unconfirmed exclusive test"
    return question, ""
