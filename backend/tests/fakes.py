"""A stand-in for the Fire client. Tests never call the real API."""

import json

from app.services.fire import ChatResult, FireResult

ANALYSIS = {
    "role_title": "Backend Engineer",
    "field": "software engineering",
    "seniority": "mid",
    "competencies": [
        {"name": "API design", "description": "Designs clean HTTP APIs"},
        {"name": "Databases", "description": "Models and tunes SQL data"},
    ],
    "formats": ["behavioral", "resume_deepdive", "technical", "coding"],
    "licensed_field": False,
}

PLAN = {
    "sections": [
        {
            "name": "Background",
            "module": "resume_deepdive",
            "minutes": 3,
            "questions": ["Walk me through your Acme project."],
        },
        {
            "name": "Technical",
            "module": "technical",
            "minutes": 5,
            "questions": [
                "How would you design a rate limiter?",
                "How do you index a slow query?",
            ],
        },
    ],
    "reserve": [
        {"section": "Technical", "text": "What is your favorite database and why?"}
    ],
}

RUBRIC = {
    "criteria": [
        {"name": "API design", "kind": "role", "weight": 0.4, "description": "d"},
        {"name": "Structure", "kind": "universal", "weight": 0.2, "description": "d"},
        {"name": "Clarity", "kind": "universal", "weight": 0.2, "description": "d"},
        {"name": "Relevance", "kind": "universal", "weight": 0.2, "description": "d"},
    ]
}


SCORE = {
    "criteria": [
        {"name": "API design", "score": 4, "comment": "Clear ownership of the API."},
        {"name": "Structure", "score": 3, "comment": "Wandered a little."},
        {"name": "clarity", "score": 4, "comment": "Easy to follow."},
        {"name": "Relevance", "score": 2, "comment": "Drifted off topic."},
        {"name": "Not in the rubric", "score": None, "comment": ""},
    ],
    "summary": "Good ownership; the result was missing.",
    "weak_moments": [
        {"quote": "My answer", "why": "Too vague."},
        {"quote": "something the candidate never said", "why": "Invented."},
        {"quote": "My answer", "why": "The transcription error sounds unprofessional."},
    ],
    "missing_points": [
        {"point": "A measurable result", "covered": False},
        {"point": "Their own role", "covered": True},
    ],
    "star": {
        "situation": True,
        "task": True,
        "action": True,
        "result": False,
        "note": "No result given.",
    },
    "stronger_version": [
        {
            "text": "At Acme I built the billing API.",
            "source": "Built the Acme billing API",
        },
        {"text": "That led to [add the result you achieved].", "source": None},
    ],
    "changes": [{"kind": "added", "text": "A result", "reason": "Shows impact."}],
    "tips": ["Name the scale you worked at."],
    "strengths": ["Owned the billing API end to end.", "  "],
    "confidence": "medium",
    "confidence_note": "Part of the answer may have been misheard.",
}

REPAIR = {
    "stronger_version": [
        {
            "text": "I built the Acme billing API.",
            "source": "Built the Acme billing API",
        },
        {"text": "The result was [add the result you achieved].", "source": None},
    ]
}

SUMMARY = {
    "reasoning": "Solid ownership, but results were missing.",
    "takeaways": ["Quantify results.", "Lead with the point.", "Keep answers tight."],
    "exercises": [
        "Write three STAR stories that end with a number.",
        "Time a 2-minute answer.",
    ],
}


GAPS = {
    "summary": "Good backend fit; no payments experience.",
    "requirements": [
        {
            "requirement": "API design",
            "status": "covered",
            "evidence": "Built the Acme billing API",
            "likely_question": "How did you version it?",
        },
        {
            "requirement": "MySQL tuning",
            "status": "covered",
            "evidence": "tuned Oracle clusters",
            "likely_question": None,
        },
        {
            "requirement": "Payments domain",
            "status": "missing",
            "evidence": "built payment rails",
            "likely_question": "How would you learn the payments domain?",
        },
    ],
}

REVERSE_CANDIDATE = {
    "name": "Sam",
    "headline": "Backend engineer, 4 years, payments",
    "resume": ["Led the payments API rewrite", "Cut errors by 90%"],
    "hidden": {
        "truths": ["Fixed bugs on the payments API", "Joined the rewrite late"],
        "exaggerations": ["Did not lead the rewrite; a teammate did"],
        "strengths": ["Debugging"],
        "weaknesses": ["Little design ownership"],
        "answer_style": "confident until asked for specifics",
    },
}
REVERSE_JUDGE = {
    "judgment": {"score": 2, "comment": "Hired without probing the leadership claim."},
    "questioning": {"score": 3, "comment": "Good opener, no follow-up on numbers."},
    "question_feedback": [
        {"question": "Tell me about the rewrite.", "score": 3, "comment": "Fine start."}
    ],
    "missed_signals": ["Never asked who led the rewrite."],
    "good_moves": ["Opened with their biggest claim."],
    "unfair_questions": [],
    "tips": ["Ask 'what exactly did you do?' after every big claim."],
}

DECODE = {
    "role_title": "Backend Engineer",
    "summary": "A backend role that likely centres on talking to stakeholders.",
    "team_size": {
        "guess": "small team",
        "why": "one product",
        "evidence": "invented words",
    },
    "pace": {
        "guess": "fast-moving",
        "why": "ship weekly",
        "evidence": "ship features every week",
    },
    "priorities": [
        {
            "point": "Keeping stakeholders aligned",
            "evidence": "work closely with stakeholders",
        },
        {"point": "Made up", "evidence": "a phrase that is not in the posting"},
    ],
    "green_flags": [
        {"point": "Mentoring", "evidence": "mentoring from senior engineers"}
    ],
    "red_flags": [{"point": "Always on", "evidence": "available around the clock"}],
    "likely_questions": [
        {
            "question": "How do you handle conflicting stakeholder asks?",
            "why": "stakeholders x4",
        }
    ],
    "competencies": [{"name": "Communication", "why": "stakeholders"}],
}


COMPANY = {
    "company": "Acme Pay",
    "summary": "Acme Pay builds billing software for small shops.",
    "talking_points": ["Billing for small shops", "Open API for partners"],
    "why_us_questions": [
        "What draws you to building billing tools for small shops?",
        "How would you help our partner API grow?",
    ],
}


class FakeFire:
    """Answers by prompt type; interviewer turns come from `turns` (else next_question)."""

    price = 0.001

    def __init__(self):
        self.calls: list[dict] = []
        self.turns: list[dict | str] = []
        # Queued scorer replies; an Exception instance is raised instead.
        self.scores: list[dict | str | Exception] = []
        # Queued rewrite-repair replies (default: one grounded sentence).
        self.repairs: list[dict | str] = []
        # What the JD analysis and plan prompts return (override per test).
        self.analysis: dict = ANALYSIS
        self.plan: dict | str = PLAN
        self.transcripts: list[str] = []
        self.audio: list[str] = []
        # Speech calls as (text, voice); set speech_error to make them fail.
        self.spoken: list[tuple[str, str | None]] = []
        self.speech_models: list[str | None] = []
        self.speech_error: Exception | None = None
        self.small_talk_error: Exception | None = None
        self.small_talk_reply = "Doing well, thanks for asking!"
        self.decode: dict = DECODE
        self.reverse_candidate: dict = REVERSE_CANDIDATE
        self.gaps: dict = GAPS
        self.company: dict = COMPANY
        self.next_round: dict | Exception = {
            "questions": [
                {
                    "question": "Walk me through a schema you designed.",
                    "why": "MySQL",
                    "module": "technical",
                },
                {
                    "question": "Tell me about a time you disagreed with a teammate.",
                    "why": "teamwork",
                    "module": "behavioral",
                },
                {
                    "question": "What would you ask the CEO?",
                    "why": "culture",
                    "module": "juggling",
                },
            ]
        }
        # Story-extraction replies (default: no stories).
        self.stories: list[dict | Exception] = []
        # Gap-check replies (T-72).
        self.gap_checks: list[dict | Exception] = []
        # Second opinion on a "didn't answer" verdict (T-112); default agrees.
        self.answer_checks: list[dict | Exception] = []
        # Did they talk about a general question's subject (T-142); default yes.
        self.subject_checks: list[dict | Exception] = []
        # Replies to "Do you have any questions for me?" turns.
        self.candidate_replies: list[dict | Exception] = []

    def chat(
        self, messages, system_prompt=None, max_tokens=1024, temperature=0.4, model=None
    ):
        prompt = messages[0]["content"]
        self.calls.append(
            {
                "prompt": prompt,
                "messages": messages,
                "model": model,
                "temperature": temperature,
            }
        )
        if "Analyze this job description" in prompt:
            body = self.analysis
        elif "question plan" in prompt:
            body = self.plan
        elif "scoring rubric" in prompt:
            body = RUBRIC
        elif "Score one question" in prompt:
            body = self.scores.pop(0) if self.scores else SCORE
            if isinstance(body, Exception):
                raise body
        elif "attempted the question they were asked" in prompt:
            body = (
                self.answer_checks.pop(0)
                if self.answer_checks
                else {"attempts": False, "quote": None}
            )
            if isinstance(body, Exception):
                raise body
        elif "talked about what the question asks about" in prompt:
            body = (
                self.subject_checks.pop(0)
                if self.subject_checks
                else {"asks_for": "x", "quote": None, "on_subject": True}
            )
            if isinstance(body, Exception):
                raise body
        elif "Check which points a candidate covered" in prompt:
            # Default: no verdicts, so the scorer's own stand (T-72).
            body = self.gap_checks.pop(0) if self.gap_checks else {"points": []}
            if isinstance(body, Exception):
                raise body
        elif "summary for a practice-interview" in prompt:
            body = SUMMARY
        elif 'Fix a "stronger version"' in prompt:
            body = self.repairs.pop(0) if self.repairs else REPAIR
        elif "whether they have any questions for you" in prompt:
            body = (
                self.candidate_replies.pop(0)
                if self.candidate_replies
                else {"has_question": False, "answer": "No problem at all."}
            )
            if isinstance(body, Exception):
                raise body
        elif "Draft a short thank-you email" in prompt:
            body = {
                "subject": "Thank you for today",
                "body": "Hi [Interviewer's name],\n\nThank you for talking with me about the backend role and the billing API work. I enjoyed it.\n\nBest,\nAda",
            }
        elif "prepare smart questions to ask the interviewer" in prompt:
            body = {
                "questions": [
                    {
                        "question": "What would success look like in the first 90 days?",
                        "why": "shows you plan",
                        "topic": "role",
                    },
                    {
                        "question": "How does the team handle on-call?",
                        "why": "the posting mentions it",
                        "topic": "team",
                    },
                ],
                "avoid": ["Asking about salary in the first round."],
            }
        elif "Rate the candidate's questions" in prompt:
            body = {
                "questions": [
                    {
                        "asked": "What does a typical week look like?",
                        "score": 3,
                        "comment": "Fine but generic.",
                        "better": "What would my first project be?",
                    },
                    {
                        "asked": "Do you offer free lunch?",
                        "score": 1,
                        "comment": "Perks first.",
                        "better": None,
                    },
                ],
                "summary": "Ask about the work, not perks.",
            }
        elif 'Help them prepare for "Why do you want to work here?"' in prompt:
            body = self.company
        elif "Compare a candidate's résumé with a job description" in prompt:
            body = self.gaps
        elif "Create a realistic job candidate" in prompt:
            body = self.reverse_candidate
        elif "Stay in character as the candidate" in prompt:
            body = {"answer": "I led the payments API rewrite and cut errors a lot."}
        elif "performance as an INTERVIEWER" in prompt:
            body = REVERSE_JUDGE
        elif "Predict what the next round will likely ask" in prompt:
            body = self.next_round
            if isinstance(body, Exception):
                raise body
        elif "Read between the lines of a job description" in prompt:
            body = self.decode
        elif "reusable interview stories" in prompt:
            body = self.stories.pop(0) if self.stories else {"stories": []}
            if isinstance(body, Exception):
                raise body
            if callable(body):  # built from the answer ids in the prompt
                body = body(prompt)
        elif "asked for a hint" in prompt:
            body = {"hint": "Think about where the requests are counted."}
        elif "moment of small talk" in prompt:
            if self.small_talk_error:
                raise self.small_talk_error
            body = {"message": self.small_talk_reply}
        elif self.turns:
            body = self.turns.pop(0)
        else:
            body = {"action": "next_question", "message": "Thanks. Next question."}
        content = body if isinstance(body, str) else json.dumps(body)
        return ChatResult(content=content, price_usd=self.price)

    def transcribe(self, audio_data_url):
        self.audio.append(audio_data_url)
        text = self.transcripts.pop(0) if self.transcripts else "I led the billing API."
        return FireResult(data={"text": text}, price_usd=0.0003)

    def speech(self, text, voice=None, model=None):
        if self.speech_error:
            raise self.speech_error
        self.spoken.append((text, voice))
        self.speech_models.append(model)
        return FireResult(data={"audio": "QUJD", "format": "mp3"}, price_usd=0.0002)

    def kinds(self) -> list[str]:
        out = []
        for c in self.calls:
            p = c["prompt"]
            for marker, kind in (
                ("Analyze this job description", "analysis"),
                ("question plan", "plan"),
                ("scoring rubric", "rubric"),
                ("Score one question", "score"),
                ("Check which points a candidate covered", "gap"),
                ("attempted the question they were asked", "answer_check"),
                ("talked about what the question asks about", "subject_check"),
                ("summary for a practice-interview", "summary"),
                ('Fix a "stronger version"', "repair"),
            ):
                if marker in p:
                    out.append(kind)
                    break
            else:
                out.append("turn")
        return out
