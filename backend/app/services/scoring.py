"""Score one question (main answer + follow-ups) and write its stronger version.

One Fire chat call per question covers scores, missing points, weak moments, STAR
and the rewrite. The weighted score is computed here, not by the model, and so is
the check that the rewrite only uses facts the candidate gave (one repair call if
it doesn't; sentences that still aren't grounded are dropped).
"""

import json
import logging
import re
from difflib import SequenceMatcher
from string import Template
from typing import Literal, get_args

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    ValidationInfo,
    model_validator,
)

from .. import modules
from ..extensions import db
from ..models import Document, Evaluation, Session
from .analytics import Clip, delivery, word_count
from .fire import FireError
from . import planning
from .llm import chat_json, render

log = logging.getLogger(__name__)

SYSTEM = (
    "You are an expert, fair interview coach. You give honest practice feedback and "
    "never invent facts about the candidate. Reply with a single JSON object only, "
    "no prose and no code fences."
)
MAX_RESUME_CHARS = 6000
VERDICTS = ((4.0, "hire"), (3.0, "lean hire"), (0.0, "no hire"))
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[a-z]+|\d+")
DIGITS_RE = re.compile(r"\d+")
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")
# Clauses are checked too, so one invented add-on ("…, ensuring they were optimized
# for performance") can't hide behind a well-grounded start.
# "I'd use a token bucket" is a plan, not experience (live check, Phase 5).
HYPOTHETICAL_RE = re.compile(
    r"\b(?:i|we)(?:'|\u2019)d\b|\b(?:i|we) (?:would|might|could|will)\b"
    r"|\b(?:i|we)(?:'|\u2019)ll\b",
    re.IGNORECASE,
)
SOURCE_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")
# A stronger version doesn't hedge: "I'm not sure about that one; I'd look at…" keeps
# only the point (live check, T-24).
HEDGE_RE = re.compile(
    r"\bi(?:(?:'|\u2019)?m| am) not (?:sure|certain)\b[^,;:.!?]*(?:[,;:.!?]+|$)\s*(?:but\s+)?"
    r"|\bi (?:don(?:'|\u2019)?t|do not) (?:know|remember)\b[^,;:.!?]*(?:[,;:.!?]+|$)\s*(?:but\s+)?",
    re.IGNORECASE,
)
# Impact claims a rewrite must not add (T-29: "…which significantly improved user
# engagement" when the candidate never said so): intensifiers, and "improved X"
# outcomes, unless the candidate's own words make the same claim.
INTENSIFIER_RE = re.compile(
    r"\b(?:significantly|greatly|dramatically|substantially|considerably|massively|"
    r"hugely|vastly|tremendously|drastically)\b",
    re.IGNORECASE,
)
OUTCOME_RE = re.compile(
    r"\b(?:improv|increas|boost|rais|enhanc|grew|grow|drove|driv)\w*\s+(?:\w+\s+){0,2}?"
    r"(engagement|satisfaction|retention|conversion|morale|revenue|sales|productivity|"
    r"efficiency|adoption|usage)\b",
    re.IGNORECASE,
)
CLAUSE_RE = re.compile(r"[,;:\u2014]|\s(?:which|while|ensuring|allowing|so that)\s")
# A rewrite sentence must share at least this share of its content words with the
# résumé + answers. Calibrated on live gpt-4o-mini rewrites: invented sentences
# ("I also collaborated closely with product teams…") scored 0–0.35, grounded
# ones 0.5+.
MIN_OVERLAP = 0.5
STOPWORDS = frozenset(
    """a an the and or but so to of in on at for with by from as is was were be been
    being it its this that these those i me my we our us you your they them their he
    she his her which who what when where how why than then there here also just very
    more most some any all each both into onto over under about after before while
    during not no only own same such too can could would should will shall may might
    must do does did done have has had having make made get got one way well really
    able""".split()
)
# Units and framing words a faithful rewrite adds ("300ms" → "300 milliseconds",
# "to address this, I…") without adding a fact.
NEUTRAL = frozenset(
    """second seconds milliseconds minute minutes hour hours day days week weeks month
    months year years percent million millions thousand billion address addressed
    issue issues cut reduce reduced reducing result resulted example""".split()
)
# Words every interview question uses; they don't make a résumé line relevant.
QUESTION_WORDS = frozenset(
    """tell walk describe share time times approach specific example examples
    experience challenge challenges faced face ensure successful success role roles
    project projects work worked process handle handled think explain""".split()
)
PAST_VERB_RE = re.compile(
    r"^(?:\w+ed|built|wrote|led|ran|made|grew|taught|won|set|drove|took|kept|"
    r"shipped|began|chose|did|got|held|lost|met|paid|put|read|saw|sold|spent|"
    r"stood|told|thought|understood)$",
    re.IGNORECASE,
)
FALLBACK_STEPS = (
    "[Describe one specific time: the situation, what you did, and the result.]"
)
# Off-topic answers to a problem (not a story): how to answer it, no résumé story.
SOLVE_FALLBACK = {
    "coding": "[Restate the problem and one example in a sentence.] [Explain your approach "
    "and its time and space complexity.] [Write the code in the editor and walk through it "
    "on the example.] [Say which edge cases you'd test.]",
    "system_design": "[Clarify the requirements and the scale.] [Name the main components "
    "and how data flows between them, and sketch them on the whiteboard.] [Explain one "
    "trade-off you made and how the design handles load or a failure.]",
    "technical": "[Answer the question directly in one sentence.] [Explain how it works "
    "or why.] [Give a trade-off or an example from your own work.]",
    "case": "[Restate the problem and your goal.] [Lay out the 2–3 parts you'd break it "
    "into.] [Work through the most important part with numbers.] [Give a recommendation.]",
}
FALLBACK_REWRITE = (
    "[Answer the question with one specific example from your experience: "
    "the situation, what you did, and the result.]"
)


RETRY_RULE = (
    "- This answer is a retry of the same question. Score EVERY criterion in the "
    "rubric above from 1 to 5 (no nulls), on the same scale as the first attempt "
    "below: raise a criterion where the new answer fixes the weakness its comment "
    "names, keep it where the answer is just as good, and lower it only where the "
    "new answer is actually worse. Rewording the same content is not an improvement. "
    "Don't mark down words that are clearly speech-recognition slips.\n"
    "  First attempt (JSON): $previous\n"
)
# Fewer words than this (all answers to the question together) can't be scored:
# the scorer filled the gap from the résumé (T-33: "so" scored 3.27).
MIN_SCORABLE_WORDS = 8
# Greetings and pleasantries: an answer made only of these didn't answer (T-61).
SMALL_TALK = frozenset(
    """hi hello hey hiya morning afternoon evening nice meet meeting meeting good
    great fine well okay ok doing thanks thank you guys everyone all how are i'm im
    am m s re ve today day going pleasure glad happy be here too and yourself yours what about
    hope also not bad pretty really so much lovely""".split()
)
NOT_ANSWERED = (
    "This didn't answer the question{what}, so it scores 1. Answer the question "
    "itself next time"
)
SMALL_TALK_NOTE = "; small talk is fine at the start, before the first question."
# The scorer's guard (T-61) catches off-topic answers, not greetings (T-71).
OFF_TOPIC_NOTE = (
    ": if you're unsure what it's asking, ask the interviewer to clarify or "
    "for a hint."
)
# Share of the scorer's evidence quote that must really be in the answer.
QUOTE_MATCH = 0.6
RESULT_POINT_RE = re.compile(
    r"\b(results?|outcomes?|impact|metrics?|measurable|quantif)", re.I
)
# A missing point about one STAR part is covered by a verified quote for it.
STAR_POINT_RE = {
    "situation": re.compile(r"\b(situation|context|background|initial state)", re.I),
    "actions": re.compile(r"\b(actions?|steps?)\b", re.I),
    "result": RESULT_POINT_RE,
}
# Words that say a "result" didn't actually happen or isn't known (T-74: "I can't
# recall the exact result", "the outcome was still mixed" counted as results).
VAGUE_RESULT_RE = re.compile(
    r"\b(?:can'?t|cannot|couldn'?t|don'?t|do not|didn'?t) (?:really )?"
    r"(?:recall|remember|know|say|tell|measure|track)"
    r"|\bnot (?:sure|certain|clear)\b|\bno idea\b|\bhard to (?:say|tell|measure)\b"
    r"|\bunclear\b|\b(?:was|were|is|are) (?:still |kind of |pretty )?mixed\b"
    r"|\bwent (?:fine|ok|okay|alright|all right|well enough|smoothly)\b"
    r"|\bworked out\b|\bfelt like\b|\bseemed (?:like|to)\b|\bpositive step\b"
    r"|\bi (?:think|guess|hope|believe) it (?:helped|worked|went)",
    re.I,
)
# A low role score whose comment only says the skill wasn't shown (T-74).
ABSENT_RE = re.compile(
    r"\b(?:did not|didn'?t|does not|doesn'?t|no) (?:mention|provide|discuss|address"
    r"|cover|show|describe|give|elaborate|include)|\bnot mentioned\b"
    r"|\bno (?:evidence|example|mention)\b",
    re.I,
)
TOO_SHORT = (
    "This answer was too short to score ({n} words). Answer with one specific "
    "example: the situation, what you did, and the result."
)


def _item_model(annotation) -> type[BaseModel] | None:
    """X for a list[X] field whose items are models, else None."""
    args = get_args(annotation)
    item = args[0] if args else None
    return item if isinstance(item, type) and issubclass(item, BaseModel) else None


def _fits(model: type[BaseModel], value) -> bool:
    try:
        model.model_validate(value)
        return True
    except ValidationError:
        return False


class Lenient(BaseModel):
    """Cut texts and lists that run past their limits and drop list entries that
    don't fit, at every level, instead of rejecting the whole score: one long list
    failed a report twice (T-93), and a long recalled answer overflowed a nested
    quote on every retry (T-105)."""

    @model_validator(mode="before")
    @classmethod
    def trim_overlong(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for name, f in cls.model_fields.items():
            if name not in data:
                continue
            v = data[name]
            item = _item_model(f.annotation)
            if item is not None and isinstance(v, list):
                v = [x for x in v if _fits(item, x)]
            limit = next(
                (m.max_length for m in f.metadata if getattr(m, "max_length", None)),
                None,
            )
            if limit and isinstance(v, (list, str)) and len(v) > limit:
                v = v[:limit]
            data[name] = v
        return data


class CriterionScore(Lenient):
    name: str = Field(min_length=1, max_length=120)
    score: int | None = Field(default=None, ge=1, le=5)  # None: not tested here
    comment: str = Field(default="", max_length=400)


class WeakMoment(Lenient):
    quote: str = Field(min_length=1, max_length=400)
    why: str = Field(min_length=1, max_length=300)


class MissingPoint(Lenient):
    point: str = Field(min_length=1, max_length=300)
    covered: bool
    # The candidate's words that cover it; checked against the answers (T-68).
    evidence: str | None = Field(default=None, max_length=600)


class Star(Lenient):
    situation: bool
    task: bool
    action: bool
    result: bool
    note: str = Field(default="", max_length=300)
    # Where the candidate says how it turned out; checked against the answers.
    result_quote: str | None = Field(default=None, max_length=600)


class Said(Lenient):
    """What the candidate actually said, copied word for word before any judging:
    extracting first makes a small model notice results it otherwise misses (T-68)."""

    situation: str | None = Field(default=None, max_length=600)
    task: str | None = Field(default=None, max_length=600)
    actions: list[str] = Field(default_factory=list, max_length=8)
    result: str | None = Field(default=None, max_length=600)
    other: list[str] = Field(default_factory=list, max_length=8)


class Change(Lenient):
    kind: Literal["added", "cut", "reframed"]
    text: str = Field(min_length=1, max_length=400)
    reason: str = Field(default="", max_length=300)


class Sentence(Lenient):
    text: str = Field(min_length=1, max_length=4000)
    source: str | None = Field(default=None, max_length=1000)


class RewriteOut(Lenient):
    stronger_version: list[Sentence] = Field(min_length=1, max_length=25)


class ScoreOut(Lenient):
    criteria: list[CriterionScore] = Field(min_length=1, max_length=12)
    summary: str = Field(min_length=1, max_length=600)
    weak_moments: list[WeakMoment] = Field(default_factory=list, max_length=5)
    missing_points: list[MissingPoint] = Field(default_factory=list, max_length=8)
    star: Star | None = None
    # May be empty (e.g. "Any questions for us?" has nothing to rewrite): the
    # rewrite then starts from the résumé instead of failing the score (T-105).
    stronger_version: list[Sentence] = Field(default_factory=list, max_length=25)
    changes: list[Change] = Field(default_factory=list, max_length=8)
    tips: list[str] = Field(default_factory=list, max_length=3)
    # What the candidate did well, each tied to something they said.
    strengths: list[str] = Field(default_factory=list, max_length=3)
    # Does the answer attempt the question at all, and where (verified, T-61)?
    answers_question: bool = True
    answer_quote: str | None = Field(default=None, max_length=600)
    said: Said | None = None
    # How sure the AI is of this judgment, and why (e.g. a garbled transcript).
    confidence: Literal["high", "medium", "low"] = "medium"
    confidence_note: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def some_criterion_scored(self, info: ValidationInfo) -> "ScoreOut":
        if all(c.score is None for c in self.criteria):
            raise ValueError("score at least one criterion")
        # A retry must be scored on the criteria its first attempt was (T-29).
        required = (info.context or {}).get("required") or []
        scored = {_norm(c.name) for c in self.criteria if c.score is not None}
        missing = [n for n in required if _norm(n) not in scored]
        if missing:
            raise ValueError(
                f"score every listed criterion; missing: {', '.join(missing)}"
            )
        return self


def _norm(text: str) -> str:
    return SPACE_RE.sub(" ", text).strip().lower()


def _stem(word: str) -> str:
    return word[:5]


def _content_words(text: str) -> list[str]:
    words = WORD_RE.findall(PLACEHOLDER_RE.sub(" ", text).lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS | NEUTRAL]


def _adds_details(text: str, stems: set[str]) -> bool:
    """Most of the sentence (or of one of its clauses) isn't in the sources."""
    for part in [text, *CLAUSE_RE.split(text)]:
        content = _content_words(part)
        novel = sum(_stem(w) not in stems for w in content)
        # A single linking word ("That led to [the result]") is fine.
        if novel >= 2 and novel / len(content) > 1 - MIN_OVERLAP:
            return True
    return False


def _without_hedge(text: str) -> str:
    text = HEDGE_RE.sub("", text).strip()
    return text[:1].upper() + text[1:]


def split_sentences(items: list[Sentence]) -> list[Sentence]:
    """The model sometimes returns a paragraph as one item: check it sentence by
    sentence. Hedges ("I'm not sure, but…") are cut; a sentence that was only a
    hedge is dropped.
    """
    return [
        Sentence(text=_without_hedge(part), source=item.source)
        for item in items
        for part in SENTENCE_END_RE.split(item.text.strip())
        if _without_hedge(part)
    ]


def _factual(sources: list[str]) -> str:
    """The sources without hypothetical sentences ("I'd…", "I would…")."""
    return " ".join(
        part
        for text in sources
        for part in SOURCE_SENTENCE_RE.findall(text)
        if not HYPOTHETICAL_RE.search(part)
    )


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in _content_words(text)}


def stitched(sentence: str, resume: str, said: str) -> list[str]:
    """Résumé-only words in a sentence that also tells what the candidate said: a
    story from the answer tied to a résumé project, result or context they never
    connected it to (T-111: "During the development of the refunds API, I faced a
    challenge when a junior engineer I mentored shipped a migration…"). Employer
    names don't count: placing a story at their employer is not a new claim."""
    employers = set().union(*(_stems(e) for e, _ in _resume_facts(resume)), set())
    words = _content_words(PLACEHOLDER_RE.sub(" ", sentence))
    resume_stems, said_stems = _stems(resume) - employers, _stems(said)
    from_resume = sorted({w for w in words if _stem(w) in resume_stems - said_stems})
    from_answer = {_stem(w) for w in words} & (said_stems - _stems(resume))
    if len(from_resume) >= STITCH_WORDS and len(from_answer) >= STITCH_WORDS:
        return from_resume
    return []


# Résumé-only and answer-only words a sentence needs to count as stitched.
STITCH_WORDS = 2


def grounding_problems(
    sentences: list[Sentence], sources: list[str], resume: str = ""
) -> list[str]:
    """One message per sentence that isn't backed by the résumé or answers ("" if ok).

    The model's cited `source` is only a prompt for it to stay grounded (it often
    leaves it out for faithful sentences); the check is on the sentence itself. A
    sentence stated as fact must be backed by facts, not only by what the candidate
    said they would do. With `resume` (one of `sources`), a sentence may not tie
    what they said to a résumé fact they never connected it to.
    """
    answered = " ".join(src for src in sources if src is not resume) if resume else ""
    stems = {_stem(w) for w in WORD_RE.findall(" ".join(sources).lower())}
    factual = {_stem(w) for w in WORD_RE.findall(_factual(sources).lower())}
    digits = set(DIGITS_RE.findall(" ".join(sources)))
    said = " ".join(sources)
    intensifiers = {w.lower() for w in INTENSIFIER_RE.findall(said)}
    outcomes = {o.lower() for o in OUTCOME_RE.findall(said)}
    problems = []
    for s in sentences:
        text = PLACEHOLDER_RE.sub(" ", s.text)
        new_numbers = set(DIGITS_RE.findall(text)) - digits
        new_impact = {w.lower() for w in INTENSIFIER_RE.findall(text)} - intensifiers
        if not PLACEHOLDER_RE.search(s.text):
            # "That improved engagement by [add the %]" asks for the real result.
            new_impact |= {o.lower() for o in OUTCOME_RE.findall(text)} - outcomes
        if new_numbers:
            problems.append(
                f"it uses numbers the candidate never gave ({', '.join(sorted(new_numbers))})"
            )
        elif new_impact:
            problems.append(
                f"it claims an impact the candidate never stated ({', '.join(sorted(new_impact))})"
            )
        elif _adds_details(s.text, stems):
            problems.append("it adds details the candidate never gave")
        elif not HYPOTHETICAL_RE.search(s.text) and _adds_details(s.text, factual):
            problems.append(
                "it presents what the candidate said they would do as something they did"
            )
        elif resume and (linked := stitched(s.text, resume, answered)):
            problems.append(
                "it ties what the candidate said to something from their résumé "
                f"({', '.join(linked)}) that they never connected it to; tell their "
                "story as they told it"
            )
        else:
            problems.append("")
    return problems


def _resume_facts(resume: str) -> list[tuple[str, str]]:
    """(employer, fact) pairs from résumé lines like "Acme (2021–now): Built X; did Y."."""
    facts = []
    for line in resume.splitlines():
        employer, _, rest = line.partition(":")
        if not rest.strip():
            employer, rest = "", line
        employer = employer.split("(")[0].strip()
        for fact in re.split(r";|\.\s", rest):
            fact = fact.strip().rstrip(".")
            if len(fact.split()) >= 2:
                facts.append((employer, fact))
    return facts


# "[add what changed because of your work]" is score.txt's own example (T-126).
RESULT_PLACEHOLDER_RE = re.compile(
    r"\[[^\]]*\b(?:(?:result|outcome|impact)s?|what changed)\b[^\]]*\]", re.I
)


def _tells_result(text: str, quote: str) -> bool:
    """The rewrite already gives this result: its numbers, or most of its words."""
    numbers = set(DIGITS_RE.findall(quote))
    if numbers:
        return numbers <= set(DIGITS_RE.findall(text))
    words = _stems(quote)
    return not words or len(words & _stems(text)) / len(words) >= 0.6


def fill_result(stronger: str, result_quote: str | None) -> str:
    """Put the candidate's own, verified result where the rewrite asks them to
    add one: it sometimes left the result they gave out (T-107). With no such
    placeholder and the result nowhere in the rewrite (a repair dropped it, T-123),
    it goes at the end."""
    if not result_quote:
        return stronger
    quote = result_quote.strip().rstrip(".!?,;:")
    if not quote:
        return stronger
    sentence = quote[0].upper() + quote[1:] + "."
    if not RESULT_PLACEHOLDER_RE.search(stronger):
        if _tells_result(stronger, quote):
            return stronger
        return f"{stronger.strip()} {sentence}".strip()
    parts = re.split(r"(?<=[.!?])\s+", stronger.strip())
    # The rewrite already tells it elsewhere: just drop the placeholder (T-121).
    rest = " ".join(p for p in parts if not RESULT_PLACEHOLDER_RE.search(p))
    out, used = [], _norm(quote) in _norm(rest)
    for part in parts:
        if RESULT_PLACEHOLDER_RE.search(part):
            if not used:
                out.append(sentence)
                used = True
            # Other placeholders next to it ("[Add: …]" gap notes, T-46) stay.
            others = RESULT_PLACEHOLDER_RE.sub(" ", part)
            if not WORD_RE.search(PLACEHOLDER_RE.sub(" ", others).lower()):
                if kept := " ".join(PLACEHOLDER_RE.findall(others)):
                    out.append(kept)
            continue
        out.append(part)
    return " ".join(out)


# "those queries" / "these changes": a back-reference that needs something before it.
BACK_REF_RE = re.compile(r"\b(?:those|these)\s+([a-z]{3,})", re.I)


def restore_context(stronger: str, answers: list[str]) -> str:
    """The rewrite opened with "I moved those queries…" after leaving out the
    sentence that said which queries (T-127): put the candidate's own sentence that
    introduced them back in front."""
    parts = re.split(r"(?<=[.!?])\s+", stronger.strip())
    if not parts or not parts[0]:
        return stronger
    m = BACK_REF_RE.search(parts[0])
    if m is None:
        return stronger
    noun = _stem(m[1].lower())
    if noun in _stems(parts[0][: m.start()]):
        return stronger  # introduced earlier in the same sentence
    said = [x for a in answers for x in re.split(r"(?<=[.!?])\s+", a.strip()) if x]
    for sentence in said:
        if BACK_REF_RE.search(sentence) and _norm(m[0]) in _norm(sentence):
            return stronger  # reached their own back-reference first: nothing to add
        if noun in _stems(sentence):
            if _norm(sentence) in _norm(stronger):
                return stronger
            return f"{sentence.strip()} {stronger.strip()}"
    return stronger


def resume_fallback(question: str, resume: str) -> str:
    """Rewrite skeleton for an answer with nothing usable: the résumé line that fits
    the question (no Fire call), plus a placeholder for the story."""
    asked = {_stem(w) for w in _content_words(question) if w not in QUESTION_WORDS}
    best, best_hits = None, 0
    for employer, fact in _resume_facts(resume):
        hits = len(asked & {_stem(w) for w in _content_words(fact)})
        if hits > best_hits:
            best, best_hits = (employer, fact), hits
    if best is None:
        return FALLBACK_REWRITE
    employer, fact = best
    first = fact.split()[0]
    if PAST_VERB_RE.match(first):
        where = f"At {employer}, I" if employer else "I"
        return f"{where} {fact[0].lower()}{fact[1:]}. {FALLBACK_STEPS}"
    return f'[Build this from your résumé: "{fact}".] {FALLBACK_STEPS}'


# Openers that point back at the previous sentence. When that sentence was dropped
# (or there is none), linking words are cut and a "this/that/it" subject becomes a
# placeholder, so the rewrite never refers to something the user can't see.
LINK_OPENER_RE = re.compile(
    r"^(?:to address (?:this|that|these|it)|as a result|because of this|"
    r"for (?:instance|example)|additionally|also|however|in addition|then|so|"
    r"this way|that way|initially)\b[,:]?\s*",
    re.IGNORECASE,
)
ACTION_VERBS = (
    r"(?:\w+ed|cut|let|made|led|took|kept|gave|brought|meant|got|helped|saved|"
    r"enabled|ensured|allowed|caused)\b"
)
# "This change cut…" → "[What you changed] cut…"; "These keys ensured…" → "The keys…".
SUBJECT_OPENER_RE = re.compile(
    rf"^(?:(?P<det>this|that|these|those)(?: (?P<noun>[a-z]+))?|it) (?={ACTION_VERBS})",
    re.IGNORECASE,
)
VAGUE_NOUNS = frozenset(
    """change changes move fix approach step steps decision work effort improvement
    improvements solution update optimization optimizations""".split()
)
DANGLING_SUBJECT = "[What you changed] "
# The model sometimes knows a phrase was misheard and flags it anyway (live check,
# T-19): a weak moment that blames transcription isn't the candidate's fault.
MISHEARING_RE = re.compile(
    r"transcri|mishear|misheard|speech[- ]recognition|speech[- ]to[- ]text",
    re.IGNORECASE,
)


def _subject(match: re.Match) -> str:
    noun = match["noun"]
    if noun and noun.lower() not in VAGUE_NOUNS:
        return f"The {noun} "
    return DANGLING_SUBJECT


def _detach(text: str) -> str:
    """Make a sentence stand on its own once the sentence before it is gone."""
    text = LINK_OPENER_RE.sub("", text, count=1)
    text = SUBJECT_OPENER_RE.sub(_subject, text, count=1)
    return text[:1].upper() + text[1:] if text and text[0] != "[" else text


def _keep(sentences: list[Sentence], problems: list[str]) -> list[Sentence]:
    """Grounded sentences, detached from any dropped sentence they followed."""
    kept: list[Sentence] = []
    previous_kept = False
    for s, problem in zip(sentences, problems):
        if problem:
            previous_kept = False
            continue
        text = s.text if previous_kept else _detach(s.text)
        kept.append(Sentence(text=text, source=s.source))
        previous_kept = True
    return kept


def _join(sentences: list[Sentence]) -> str:
    return " ".join(SPACE_RE.sub(" ", s.text).strip() for s in sentences).strip()


def grounded_rewrite(
    user_id: int,
    sentences: list[Sentence],
    sources: list[str],
    question: str,
    resume: str,
    answers: list[str],
    words: int,
    changes: list["Change"],
) -> tuple[str, list["Change"]]:
    """The rewrite (after one repair call if any sentence isn't grounded) and the
    "what changed" list, kept only when the scorer's rewrite passed unchanged:
    otherwise it would describe text the user never sees.
    """
    sentences = split_sentences(sentences)
    problems = grounding_problems(sentences, sources, resume)
    if any(problems):
        numbered = [f"Sentence {i}: {p}." for i, p in enumerate(problems, start=1) if p]
        prompt = render(
            "rewrite_repair",
            question=question,
            resume=resume,
            answers=answers,
            sentences=[s.model_dump() for s in sentences],
            problems="\n".join(numbered),
            target_words=str(words),
        )
        repaired = chat_json(
            user_id, prompt, RewriteOut, SYSTEM, max_tokens=1200, temperature=0.2
        )
        sentences = split_sentences(repaired.stronger_version)
        changes = []
        problems = grounding_problems(sentences, sources, resume)
    kept = _keep(sentences, problems)
    if not any(WORD_RE.search(PLACEHOLDER_RE.sub(" ", s.text).lower()) for s in kept):
        # Nothing but bare placeholders left: start from the résumé instead.
        return resume_fallback(question, resume), []
    return _join(kept), changes if len(kept) == len(sentences) else []


# Relevance at or below this means the answer missed the question.
OFF_TOPIC = 2
OFF_TOPIC_SCORE = 2.5  # ...and the answer as a whole was poor
# A rewrite this similar to the answer is a copy, not a stronger version (T-46).
COPY_RATIO = 0.9
MAX_GAP_PLACEHOLDERS = 2


def copy_ratio(rewrite: str, answers: list[str]) -> float:
    """Share of the rewrite's words that are the candidate's own, in the same order
    (1.0 = a straight copy of one or more answers)."""
    a = WORD_RE.findall(PLACEHOLDER_RE.sub(" ", rewrite).lower())
    b = WORD_RE.findall(" ".join(answers).lower())
    if not a or not b:
        return 0.0
    blocks = SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(m.size for m in blocks if m.size >= 3) / len(a)


def not_a_copy(
    user_id: int,
    stronger: str,
    changes: list["Change"],
    missing: list[str],
    sources: list[str],
    question: str,
    resume: str,
    answers: list[str],
    words: int,
) -> tuple[str, list["Change"]]:
    """One repair call if the rewrite just repeats the answer; then, if it still
    does, placeholders for the gaps so it is never a copy (live check, T-46)."""
    if copy_ratio(stronger, answers) < COPY_RATIO or not missing:
        return stronger, changes
    gaps = "; ".join(missing[:4])
    prompt = render(
        "rewrite_repair",
        question=question,
        resume=resume,
        answers=answers,
        sentences=[s.model_dump() for s in split_sentences([Sentence(text=stronger)])],
        problems=(
            "The whole rewrite repeats the candidate's answer instead of improving it. "
            "Restructure it (lead with a direct answer, then specifics, then the result) "
            f"and cover these missing points, with placeholders where facts are missing: {gaps}."
        ),
        target_words=str(words),
    )
    try:
        repaired = chat_json(
            user_id, prompt, RewriteOut, SYSTEM, max_tokens=1200, temperature=0.2
        )
        sentences = split_sentences(repaired.stronger_version)
        kept = _keep(sentences, grounding_problems(sentences, sources, resume))
        text = _join(kept)
        if kept and copy_ratio(text, answers) < COPY_RATIO:
            return text, []
    except FireError as err:
        log.warning("Rewrite repair failed: %s", err)
    adds = " ".join(f"[Add: {m.rstrip('.')}.]" for m in missing[:MAX_GAP_PLACEHOLDERS])
    return f"{stronger} {adds}", []


def weighted_score(
    scores: list[CriterionScore], rubric: dict | None
) -> tuple[float, list[dict]]:
    """Weighted 1–5 score over the rubric criteria the model scored.

    Criteria the question doesn't test (score None) are left out entirely.
    """
    scores = [s for s in scores if s.score is not None]
    by_name = {_norm(s.name): s for s in scores}
    rows = []
    for c in (rubric or {}).get("criteria", []):
        s = by_name.get(_norm(c["name"]))
        if s is not None:
            rows.append(
                {
                    "name": c["name"],
                    "kind": c.get("kind", "role"),
                    "weight": c.get("weight", 0),
                    "score": s.score,
                    "comment": s.comment,
                }
            )
    # Over the criteria this answer was scored on: role 70%, communication 30%.
    for r, w in zip(rows, planning.share_weights(rows)):
        r["weight"] = round(w, 3)
    total_weight = sum(r["weight"] for r in rows)
    if not rows or total_weight <= 0:
        # The model renamed every criterion: fall back to a plain average.
        rows = [
            {
                "name": s.name,
                "kind": "role",
                "weight": 0,
                "score": s.score,
                "comment": s.comment,
            }
            for s in scores
        ]
        return round(sum(s.score for s in scores) / len(scores), 2), rows
    score = sum(r["score"] * r["weight"] for r in rows) / total_weight
    return round(score, 2), rows


def verdict_for(score: float) -> str:
    return next(v for floor, v in VERDICTS if score >= floor)


def target_words(budget_sec: int | None) -> int:
    """Length of the stronger version: ~70% of what fits the budget at 130 wpm."""
    return min(250, max(80, round((budget_sec or 120) * 130 / 60 * 0.7)))


def section_plan(session: Session, section: str) -> dict:
    for s in (session.plan_json or {}).get("sections", []):
        if s["name"] == section:
            return s
    return {}


def section_module(session: Session, section: str) -> str:
    return section_plan(session, section).get("module", modules.DEFAULT)


def small_talk(answers: list[str]) -> bool:
    """Only greetings and pleasantries ("Hi, nice to meet you, how are you?")."""
    words = WORD_RE.findall(" ".join(answers).lower().replace("’", "'"))
    return bool(words) and all(w in SMALL_TALK or w in STOPWORDS for w in words)


def quote_found(quote: str, answers: list[str]) -> bool:
    """Most of the scorer's quote is really in the answers (wording may differ)."""
    said = {_stem(w) for w in _content_words(" ".join(answers))}
    quoted = [_stem(w) for w in _content_words(quote)]
    if not quoted:
        return False
    return sum(w in said for w in quoted) / len(quoted) >= QUOTE_MATCH


class AnswerCheckOut(BaseModel):
    attempts: bool
    quote: str | None = Field(default=None, max_length=600)


ATTEMPT_NOTE = (
    "A separate check found that the candidate does attempt this question "
    '(their words: "$quote"). Set "answers_question": true and judge the answer '
    "on its merits.\n\n"
)


def attempts_question(
    user_id: int, exchange: list[dict], answers: list[str]
) -> str | None:
    """Second opinion on the scorer's "didn't answer the question" (T-112: an answer
    that listed the steps asked for was scored 1 once, 4.2 on a re-run). Returns the
    candidate's words that address the question, or None: if the check fails or
    its quote isn't really in the answers, the scorer's verdict stands."""
    prompt = render(
        "answer_check",
        exchange=[
            {k: e[k] for k in ("interviewer", "candidate", "spoken") if k in e}
            for e in exchange
        ],
    )
    try:
        out = chat_json(
            user_id, prompt, AnswerCheckOut, SYSTEM, max_tokens=200, temperature=0
        )
    except FireError as err:
        log.warning("Answer check failed, keeping the scorer's verdict: %s", err)
        return None
    if out.attempts and out.quote and quote_found(out.quote, answers):
        return out.quote.strip()
    return None


class GapVerdict(BaseModel):
    n: int
    # What exactly the point asks for, written before judging (T-72).
    needs: str = Field(default="", max_length=300)
    quote: str | None = Field(default=None, max_length=600)
    covered: bool
    # Part of a strong answer to the main question; advice that doesn't fit the
    # question ("how they handled objections" on a setback question) is dropped (T-108).
    fits: bool = True


class GapCheckOut(BaseModel):
    points: list[GapVerdict] = Field(default_factory=list, max_length=12)
    # T-114: the specific thing the main question asks about (a project, product or
    # résumé item) and what their story was about.
    named_subject: str | None = Field(default=None, max_length=200)
    story_subject: str | None = Field(default=None, max_length=200)


# Relevance for a real story about something other than what the question named.
OFF_SUBJECT_RELEVANCE = 2
OFF_SUBJECT_TIP = (
    "Tell a story about what the question names ({subject}); if you don't have "
    "one, say so and offer the closest example."
)


# A gap-check quote must match the answers more closely than the scorer's.
GAP_QUOTE_MATCH = 0.8


def check_gaps(
    user_id: int, exchange: list[dict], points: list[MissingPoint], answers: list[str]
) -> GapCheckOut | None:
    """Re-decide each missing point in a call of its own (T-72): the scorer, doing
    ten jobs at once, listed points the candidate made as gaps and credited others
    with unrelated quotes. A point counts as covered only with a quote that is
    really in the answers; if this call fails, the scorer's verdicts stand. A gap
    that doesn't fit the main question is dropped, keeping at least one point.
    Returns the check (None if it didn't run) for its subject verdict (T-114)."""
    if not points:
        return None
    prompt = render(
        "gap_check",
        exchange=[
            {k: e[k] for k in ("interviewer", "candidate", "spoken") if k in e}
            for e in exchange
        ],
        points="\n".join(f"{i}. {m.point}" for i, m in enumerate(points, 1)),
    )
    try:
        out = chat_json(
            user_id, prompt, GapCheckOut, SYSTEM, max_tokens=900, temperature=0
        )
    except FireError as err:
        log.warning("Gap check failed, keeping the scorer's verdicts: %s", err)
        return None
    verdicts = {v.n: v for v in out.points}
    for i, m in enumerate(points, 1):
        v = verdicts.get(i)
        if v is None:
            continue
        words = [_stem(w) for w in _content_words(v.quote or "")]
        said = {_stem(w) for w in _content_words(" ".join(answers))}
        real = (
            bool(words)
            and sum(w in said for w in words) / len(words) >= GAP_QUOTE_MATCH
        )
        if v.covered and real:
            m.covered, m.evidence = True, v.quote
        else:
            m.covered, m.evidence = False, None
    unfit = {
        i
        for i, m in enumerate(points, 1)
        if not m.covered and i in verdicts and not verdicts[i].fits
    }
    if unfit and len(unfit) < len(points):
        points[:] = [m for i, m in enumerate(points, 1) if i not in unfit]
    return out


def cap_off_subject(
    criteria: list[CriterionScore],
    check: GapCheckOut | None,
    answers: list[str],
    resume: str,
    general_off: bool = False,
) -> tuple[str, str] | None:
    """A real story about something other than the résumé item the question named
    (T-114: asked about building the refunds API, they told a migration story; it
    scored 3.67) gets Relevance at most 2. The model names the subject well but
    judges a match leniently, so the match is decided in code: at least two of the
    subject's words are in the résumé (a résumé item, not a category like
    "optimizing a backend process") and none of those appear in their answers.
    A subject that isn't a résumé item ("optimizing a PostgreSQL schema") is capped
    when `general_off`: off_general_subject() found they never talked about it.
    Returns (named subject, story subject) when it capped Relevance."""
    subject = ((check.named_subject or "") if check else "").strip().rstrip(".")
    item = subject_item(subject, resume)
    said = _roots(" ".join(answers)) | _metrics(" ".join(answers))
    if len(item) < SUBJECT_WORDS:
        if not general_off:
            return None
    elif (item | _metrics(subject)) & said:
        return None
    story = (check.story_subject or "something else").strip().rstrip(".")
    for c in criteria:
        if _norm(c.name) == "relevance" and c.score is not None:
            if c.score > OFF_SUBJECT_RELEVANCE:
                c.score = OFF_SUBJECT_RELEVANCE
                c.comment = (
                    f"The question asked about {subject}, but the story was about "
                    f"{story}."
                )
            return subject, story
    return None


class SubjectCheckOut(BaseModel):
    asks_for: str = Field(default="", max_length=300)
    quote: str | None = Field(default=None, max_length=600)
    on_subject: bool


def general_subject(check: GapCheckOut | None, resume: str) -> str | None:
    """The named subject when it is a general one (not a résumé item, and more than
    question words: "optimizing a PostgreSQL database schema"), else None."""
    subject = ((check.named_subject or "") if check else "").strip().rstrip(".")
    named = _roots(subject) - {_root(w) for w in QUESTION_WORDS}
    if (
        len(named) < SUBJECT_WORDS
        or len(subject_item(subject, resume)) >= SUBJECT_WORDS
    ):
        return None
    return subject


def off_general_subject(
    user_id: int, question: str, subject: str, answers: list[str]
) -> bool:
    """T-142 (live): asked how they'd optimize a PostgreSQL schema, they described
    idempotency keys "stored in PostgreSQL" and kept Relevance 4. Words can't match a
    general subject (a good answer says "indexes" and "partitioning"), and the gap
    check, doing several jobs and reading the interviewer's drifting follow-up,
    judged it on subject. So one narrow call sees only the question and their words.
    Only a clear "no" counts; a failed call never caps."""
    prompt = render(
        "subject_check", question=question, subject=subject, answers=answers
    )
    try:
        out = chat_json(
            user_id, prompt, SubjectCheckOut, SYSTEM, max_tokens=300, temperature=0
        )
    except FireError as err:
        log.warning("Subject check failed, keeping Relevance: %s", err)
        return False
    return not out.on_subject


# Rewrite skeleton for a general question answered about something else: their story
# doesn't answer it, so the rewrite says how to (T-142).
GENERAL_OFF_SUBJECT_REWRITE = (
    "[Answer what the question asks about, {subject}, directly in one sentence.] "
    "[Explain how you'd do it and why.] [Give a trade-off, or an example from your "
    "own work.]"
)


# A summary sentence that calls the answer relevant or on topic.
RELEVANT_CLAIM_RE = re.compile(
    r"\b(?:relevant|on[- ]topic|(?:directly |clearly )?(?:address|answer)(?:s|ed)? "
    r"the question)\b",
    re.IGNORECASE,
)


def off_subject_summary(summary: str, subject: str, story: str) -> str:
    """T-118: Relevance was capped in code, so the model's summary may still call the
    story relevant; such sentences go and the summary says what happened."""
    kept = [
        x
        for x in re.split(r"(?<=[.!?])\s+", summary.strip())
        if x and not RELEVANT_CLAIM_RE.search(x)
    ]
    lead = f"The story was about {story}, but the question asked about {subject}."
    return " ".join([lead, *kept])


# "p95", "1.8", "300", "4%": WORD_RE splits or drops them, but naming the metric the
# question asked about is being on subject (T-120: "p95 dropped from 1.8 seconds";
# T-128: "the retry rate went from 4% to 1%").
METRIC_RE = re.compile(r"\b[a-z]+\d+\b|\d+(?:\.\d+)?%|\d+\.\d+|\d{2,}")

# Endings dropped before comparing subject words, so "retry" matches "retries" and
# "fails" matches "failed" (T-128: five-letter stems kept them apart).
ENDINGS = (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", ""))


def _root(word: str) -> str:
    for end, repl in ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            word = word[: -len(end)] + repl
            break
    return word[:5]


def _roots(text: str) -> set[str]:
    return {_root(w) for w in _content_words(text)}


def subject_item(subject: str, resume: str) -> set[str]:
    """The named subject's words that are in the résumé, minus generic question words."""
    return _roots(subject) & _roots(resume) - {_root(w) for w in QUESTION_WORDS}


def _metrics(text: str) -> set[str]:
    return set(METRIC_RE.findall(text.lower()))


def drop_named_subject(
    stronger: str, item: set[str], resume: str = "", answers: list[str] = ()
) -> str:
    """An off-subject story's rewrite tells the story they told; sentences about the
    résumé item the question named go, and so do résumé facts they never tied to
    this story (T-129: "I was responsible for the reliability of the refunds API…"
    and "I also implemented idempotency keys…" were added to a migration story).
    Employer names don't count. "" when nothing of their story is left."""
    employers = set().union(*(_roots(e) for e, _ in _resume_facts(resume)), set())
    resume_only = _roots(resume) - _roots(" ".join(answers)) - employers

    def grafted(part: str) -> bool:
        return len(_roots(part) & resume_only) >= STITCH_WORDS

    parts = re.split(r"(?<=[.!?])\s+", stronger.strip())
    kept = [p for p in parts if p and not _roots(p) & item and not grafted(p)]
    if not any(WORD_RE.search(PLACEHOLDER_RE.sub(" ", p).lower()) for p in kept):
        return ""
    return " ".join(kept)


# Résumé words a named subject needs to count as a résumé item (T-114).
SUBJECT_WORDS = 2


def states_outcome(quote: str | None) -> bool:
    """The quote says what happened: a number, or wording that isn't a non-result."""
    if not quote:
        return False
    text = quote.replace("’", "'")
    return bool(re.search(r"\d", text)) or not VAGUE_RESULT_RE.search(text)


def drop_untested(
    criteria: list[CriterionScore], rubric: dict, question: str
) -> list[CriterionScore]:
    """A role criterion scored 1–2 only because the answer didn't mention it is
    one the question doesn't test (the prompt says null, T-74: "Objection handling
    2: did not mention objections" on a resilience question). Leave it out when
    the question doesn't name the skill either."""
    role = {
        _norm(c["name"]) for c in rubric.get("criteria", []) if c.get("kind") == "role"
    }
    asked = {_stem(w) for w in _content_words(question)}
    for c in criteria:
        if (
            c.score is not None
            and c.score <= 2
            and _norm(c.name) in role
            and ABSENT_RE.search(c.comment)
            and not {_stem(w) for w in _content_words(c.name)} & asked
        ):
            c.score, c.comment = None, ""
    return criteria


def verify_coverage(out: ScoreOut, answers: list[str]) -> None:
    """Decide "covered" and the STAR parts from the quoted words, not the model's
    yes/no: it marked every point uncovered and every result missing, even
    "zero double refunds since launch" (T-68). A quote that isn't in the answers
    counts as not given; with no quote, the model's own answer stands."""

    def found(quote: str | None) -> str | None:
        return quote if quote and quote_found(quote, answers) else None

    said = out.said or Said()
    star_quotes = {
        "situation": found(said.situation),
        "task": found(said.task),
        "actions": next((q for q in said.actions if found(q)), None),
        "result": next(
            (
                q
                for q in (
                    found(said.result),
                    found(out.star.result_quote if out.star else None),
                )
                if states_outcome(q)
            ),
            None,
        ),
    }
    # Only words like "I can't recall the result" or "it went fine": no outcome.
    vague_result = not star_quotes["result"] and bool(
        found(said.result) or found(out.star.result_quote if out.star else None)
    )
    for m in out.missing_points:
        if m.evidence:
            m.covered = quote_found(m.evidence, answers)
        if not m.covered and not m.evidence:
            # "Add measurable outcomes" next to a quoted result contradicts it.
            part = next(
                (k for k, r in STAR_POINT_RE.items() if r.search(m.point)), None
            )
            if part and star_quotes[part]:
                m.covered, m.evidence = True, star_quotes[part]
    if out.star is not None:
        for part, field in (
            ("situation", "situation"),
            ("task", "task"),
            ("actions", "action"),
            ("result", "result"),
        ):
            if star_quotes[part]:
                setattr(out.star, field, True)
        if star_quotes["result"]:
            out.star.result_quote = star_quotes["result"]
        elif out.star.result_quote or vague_result:
            # Quoted words the candidate never said, or no actual outcome.
            out.star.result = False
            out.star.result_quote = None


def _too_short(
    session: Session,
    answer_id: int,
    rubric: dict,
    criteria: list[str] | None,
    said: int,
    clips: list[Clip],
    budget_sec: int | None,
    resume_text: str,
    question: str,
    summary: str | None = None,
    comment: str = "The answer was too short to show this.",
    module: str | None = None,
) -> Evaluation:
    """A near-empty answer scores 1 on every criterion, without a Fire call."""
    wanted = {_norm(n) for n in criteria} if criteria else None
    rows = [
        {
            "name": c["name"],
            "kind": c.get("kind", "role"),
            "weight": c.get("weight", 0),
            "score": 1,
            "comment": comment,
        }
        for c in rubric.get("criteria", [])
        if wanted is None or _norm(c["name"]) in wanted
    ]
    evaluation = Evaluation(
        answer_id=answer_id,
        score=1.0,
        rubric_scores_json={"criteria": rows},
        missing_points_json=[],
        stronger_version=SOLVE_FALLBACK.get(module)
        or resume_fallback(question, resume_text),
        changes_json=[],
        delivery_json=delivery(clips, budget_sec),
        feedback_json={
            "summary": summary or TOO_SHORT.format(n=said),
            "weak_moments": [],
            "star": None,
            "tips": [],
            "strengths": [],
            "confidence": "high",
            "confidence_note": "",
        },
    )
    db.session.add(evaluation)
    db.session.commit()
    return evaluation


CUT_OFF_TIP = "You ran out of time; lead with your main point sooner."
CUT_OFF_SILENT = (
    "Time ran out before you answered. Under a time limit, start with your main "
    "point in one sentence, then add detail while time allows."
)


def evaluate(*args, **kwargs) -> Evaluation:
    """Score one answer (see _evaluate). An answer stopped by the time limit is
    scored on what was said, and its feedback says it was cut off (T-109)."""
    evaluation = _evaluate(*args, **kwargs)
    exchange = kwargs.get("exchange", args[5] if len(args) > 5 else [])
    if not any(e.get("cut_off") for e in exchange):
        return evaluation
    fb = dict(evaluation.feedback_json or {})
    said = sum(word_count(e["candidate"]) for e in exchange if not e.get("no_answer"))
    if said == 0:
        fb["summary"] = CUT_OFF_SILENT
    fb["tips"] = [CUT_OFF_TIP] + [t for t in fb.get("tips", []) if t != CUT_OFF_TIP][:2]
    fb["cut_off"] = True
    evaluation.feedback_json = fb
    db.session.commit()
    return evaluation


def _evaluate(
    user_id: int,
    session: Session,
    answer_id: int,
    section: str,
    budget_sec: int | None,
    exchange: list[dict],
    clips: list[Clip],
    question: str | None = None,
    criteria: list[str] | None = None,
    previous: dict | None = None,
) -> Evaluation:
    """One Fire chat call → a saved Evaluation for `answer_id`.

    `exchange` is [{"interviewer": ..., "candidate": ...}], main question first.
    `criteria` (for "Try again") limits scoring to the criteria the first attempt
    was scored on, all of them required, so before and after compare like with like;
    `previous` is that attempt ({"answer", "criteria", "summary"}) to compare against.
    """
    resume = db.session.get(Document, session.resume_id) if session.resume_id else None
    resume_text = resume.raw_text[:MAX_RESUME_CHARS] if resume else ""
    words = target_words(budget_sec)
    plan = section_plan(session, section)
    scenario = plan.get("scenario") if plan.get("module") == "roleplay" else None
    rubric = session.rubric_json or {}
    said = sum(word_count(e["candidate"]) for e in exchange)
    if said < MIN_SCORABLE_WORDS:
        return _too_short(
            session,
            answer_id,
            rubric,
            criteria,
            said,
            clips,
            budget_sec,
            resume_text,
            question or exchange[0]["interviewer"],
        )
    module = section_module(session, section)
    if not scenario and small_talk([e["candidate"] for e in exchange]):
        # Greetings only: nothing to score, and no Fire call (T-61).
        return _too_short(
            session,
            answer_id,
            rubric,
            criteria,
            said,
            clips,
            budget_sec,
            resume_text,
            question or exchange[0]["interviewer"],
            summary=NOT_ANSWERED.format(what=" (it was small talk)") + SMALL_TALK_NOTE,
            comment="The answer didn't address the question.",
            module=module,
        )
    if criteria:
        wanted = {_norm(n) for n in criteria}
        rubric = {
            **rubric,
            "criteria": [
                c for c in rubric.get("criteria", []) if _norm(c["name"]) in wanted
            ],
        }
    score_values = dict(
        role=(session.plan_json or {}).get("role_title") or "the role",
        difficulty=session.difficulty or "mid",
        module=modules.MODULES.get(module, modules.MODULES[modules.DEFAULT]).label,
        module_guidance=modules.guidance(module, "score"),
        scenario=scenario or "none",
        rubric=[
            {k: c.get(k, "") for k in ("name", "description", "strong_answer")}
            for c in rubric.get("criteria", [])
        ],
        criteria_rule=(
            Template(RETRY_RULE).substitute(previous=json.dumps(previous or {}))
            if criteria
            else ""
        ),
        resume=resume_text or "(not available)",
        exchange=exchange,
        target_words=str(words),
    )

    def score_call(attempt_note: str = "") -> ScoreOut:
        # Temperature 0: the same answer should get the same score (T-29).
        return chat_json(
            user_id,
            render("score", attempt_note=attempt_note, **score_values),
            ScoreOut,
            SYSTEM,
            max_tokens=2000,
            temperature=0,
            context={"required": criteria or []},
        )

    out = score_call()
    answers = [e["candidate"] for e in exchange]
    invented = out.answer_quote is not None and not quote_found(
        out.answer_quote, answers
    )
    if not scenario and not out.answers_question and not invented:
        # A false "no" costs the whole question: confirm it first (T-112).
        quote = attempts_question(user_id, exchange, answers)
        if quote is not None:
            log.info("Answer %s does attempt the question; scoring again", answer_id)
            out = score_call(Template(ATTEMPT_NOTE).substitute(quote=quote))
            invented = out.answer_quote is not None and not quote_found(
                out.answer_quote, answers
            )
    if not scenario and (not out.answers_question or invented):
        # The scorer says it wasn't an answer, or "quoted" words the candidate never
        # said (T-61: a greeting scored 3.56 with invented content). Score it 1.
        log.info("Answer %s didn't address the question; scoring 1", answer_id)
        return _too_short(
            session,
            answer_id,
            rubric,
            criteria,
            said,
            clips,
            budget_sec,
            resume_text,
            question or exchange[0]["interviewer"],
            summary=NOT_ANSWERED.format(what="") + OFF_TOPIC_NOTE,
            comment="The answer didn't address the question.",
            module=module,
        )
    verify_coverage(out, answers)
    gaps = check_gaps(user_id, exchange, out.missing_points, answers)
    general = None if scenario else general_subject(gaps, resume_text)
    off_subject = (
        cap_off_subject(
            out.criteria,
            gaps,
            answers,
            resume_text,
            general_off=general is not None
            and off_general_subject(
                user_id, question or exchange[0]["interviewer"], general, answers
            ),
        )
        if not scenario
        else None
    )
    if not criteria:  # "Try again" must score the same criteria as before
        drop_untested(out.criteria, rubric, question or exchange[0]["interviewer"])
    score, rows = weighted_score(out.criteria, rubric)
    relevance = next(
        (r["score"] for r in rows if _norm(r["name"]) == "relevance"), None
    )
    # A cut-off answer is unfinished, not off topic: its rewrite builds on what they
    # did say (T-130: a real failure story got the generic "answer the question").
    off_topic = (
        relevance is not None
        and relevance <= OFF_TOPIC
        and score < OFF_TOPIC_SCORE
        and not any(e.get("cut_off") for e in exchange)
    )
    if off_topic and not scenario:
        # The answer missed the question: the AI would have to stitch résumé facts
        # into a story that never happened (T-48). Point at the résumé instead, or,
        # for a problem to solve, at how to answer it (T-56).
        stronger, changes = (
            SOLVE_FALLBACK.get(module)
            or resume_fallback(question or exchange[0]["interviewer"], resume_text),
            [],
        )
    else:
        stronger, changes = grounded_rewrite(
            user_id,
            out.stronger_version,
            # In a role-play the reply may refer to what the character said.
            [resume_text, *answers]
            + (
                [e["interviewer"] for e in exchange] + list(scenario.values())
                if scenario
                else []
            ),
            question or exchange[0]["interviewer"],
            resume_text,
            answers,
            words,
            out.changes,
        )

        stronger, changes = not_a_copy(
            user_id,
            stronger,
            changes,
            [m.point for m in out.missing_points if not m.covered],
            [resume_text, *answers],
            question or exchange[0]["interviewer"],
            resume_text,
            answers,
            words,
        )
        if off_subject and general is not None:
            stronger, changes = (
                GENERAL_OFF_SUBJECT_REWRITE.format(subject=off_subject[0]),
                [],
            )
        elif off_subject:
            kept = drop_named_subject(
                stronger,
                subject_item(off_subject[0], resume_text),
                resume_text,
                answers,
            )
            if kept != stronger:
                stronger, changes = (
                    kept
                    or resume_fallback(
                        question or exchange[0]["interviewer"], resume_text
                    ),
                    [],
                )

    if not (off_topic and not scenario):
        stronger = fill_result(stronger, out.star.result_quote if out.star else None)
        stronger = restore_context(stronger, answers)
    said = _norm(" ".join(e["candidate"] for e in exchange))
    weak = [
        w.model_dump()
        for w in out.weak_moments
        if _norm(w.quote) in said and not MISHEARING_RE.search(w.why)
    ][:3]
    evaluation = Evaluation(
        answer_id=answer_id,
        score=score,
        rubric_scores_json={"criteria": rows},
        missing_points_json=[m.model_dump() for m in out.missing_points],
        stronger_version=stronger,
        changes_json=[c.model_dump() for c in changes],
        delivery_json=delivery(clips, budget_sec),
        feedback_json={
            "summary": (
                off_subject_summary(out.summary, *off_subject)
                if off_subject
                else out.summary
            ),
            "weak_moments": weak,
            "star": out.star.model_dump() if out.star else None,
            "tips": (
                [OFF_SUBJECT_TIP.format(subject=off_subject[0])] if off_subject else []
            )
            + [t for t in out.tips if t.strip()][: 1 if off_subject else 2],
            "strengths": [s for s in out.strengths if s.strip()][:3],
            "confidence": out.confidence,
            "confidence_note": out.confidence_note.strip(),
        },
    )
    db.session.add(evaluation)
    db.session.commit()
    return evaluation


def evaluation_dict(e: Evaluation | None) -> dict | None:
    if e is None:
        return None
    fb = e.feedback_json or {}
    return {
        "score": e.score,
        "criteria": (e.rubric_scores_json or {}).get("criteria", []),
        "summary": fb.get("summary", ""),
        "weak_moments": fb.get("weak_moments", []),
        "star": fb.get("star"),
        "tips": fb.get("tips", []),
        "cut_off": bool(fb.get("cut_off")),
        "strengths": fb.get("strengths", []),
        "confidence": fb.get("confidence"),
        "confidence_note": fb.get("confidence_note", ""),
        "missing_points": e.missing_points_json or [],
        "stronger_version": e.stronger_version,
        "changes": e.changes_json or [],
        "delivery": e.delivery_json,
    }
