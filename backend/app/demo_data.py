"""Fictional content for the sales demo org (T-166). Hand-written; no Fire calls.

Every person, employer and number here is made up. Scores are per rubric
criterion (1–5, None = not tested); the seed computes the weighted question
score and the report from them with the app's own scoring code.
"""

ORG = {
    "name": "Northstar Career Partners",
    "color": "#1f6f8b",
    # A small four-point star on a rounded square, as an SVG data URL.
    "logo_svg": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="14" fill="#1f6f8b"/>'
        '<path d="M32 8 L37 27 L56 32 L37 37 L32 56 L27 37 L8 32 L27 27 Z" '
        'fill="#ffffff"/><circle cx="32" cy="32" r="4" fill="#f2b134"/></svg>'
    ),
}

COACH = {"name": "Morgan Ellis", "email": "morgan.ellis"}

UNIVERSAL = ("Structure", "Clarity", "Relevance")

# Generic per-band comments for the communication criteria.
BAND_COMMENTS = {
    "Structure": {
        5: "Clear situation, action and result in order.",
        4: "Well ordered; the result could come a little sooner.",
        3: "Mostly ordered, but the point arrived late.",
        2: "Jumped between points; hard to follow the thread.",
        1: "No clear beginning, middle or end.",
    },
    "Clarity": {
        5: "Precise and easy to follow.",
        4: "Easy to follow with only small detours.",
        3: "Understandable, with some vague wording.",
        2: "Vague phrases hid what actually happened.",
        1: "Hard to tell what was said.",
    },
    "Relevance": {
        5: "Answered exactly what was asked.",
        4: "On topic throughout.",
        3: "On topic, with some drift.",
        2: "Only partly answered the question.",
        1: "Did not answer the question.",
    },
}
ROLE_COMMENTS = {
    5: "Strong, specific evidence for this skill.",
    4: "Good evidence; one more concrete detail would make it stand out.",
    3: "Some evidence, but light on specifics.",
    2: "Little concrete evidence of this skill.",
    1: "No evidence of this skill in the answer.",
}


def q(
    section,
    module,
    text,
    answer,
    _seconds,  # rough spoken length while writing; the seed derives it from pace
    scores,
    summary,
    stronger,
    missing=(),
    weak=(),
    star=None,
    tips=(),
    strengths=(),
):
    return {
        "section": section,
        "module": module,
        "text": text,
        "answer": answer,
        "scores": scores,
        "summary": summary,
        "stronger": stronger,
        "missing": list(missing),
        "weak": list(weak),
        "star": star,
        "tips": list(tips),
        "strengths": list(strengths),
    }


def star(s=True, t=True, a=True, r=True, note=""):
    return {"situation": s, "task": t, "action": a, "result": r, "note": note}


CANDIDATES = [
    # ------------------------------------------------------------------ strong
    {
        "key": "candidate",
        "name": "Alex Chen",
        "email": "alex.chen",
        "role": "Backend Software Engineer",
        "seniority": "mid",
        "licensed": False,
        "goal": 3,
        "resume": (
            "Alex Chen, Backend Software Engineer. 4 years at Harborline Freight "
            "(fictional): owns the shipment-tracking API (Python, PostgreSQL), "
            "moved webhook delivery to a queue with retries, on-call lead for a "
            "team of five, mentors two junior engineers. B.Sc. Computer Science."
        ),
        "jd": (
            "Mid-level Backend Engineer at a logistics software company. Design "
            "and own REST APIs, improve reliability of event processing, tune "
            "PostgreSQL, take part in on-call, and communicate clearly with "
            "product and support teams."
        ),
        "rubric": [
            ("API Design", "role", 0.35),
            ("Reliability", "role", 0.35),
            ("Ownership", "role", 0.3),
        ],
        "sessions": [
            {
                "days_ago": 9,
                "minutes": 10,
                "persona": "neutral",
                "takeaways": [
                    "Lead with the result, then explain how you got there.",
                    "Name your own part, not just the team's.",
                    "Put a number on the impact.",
                ],
                "reason": (
                    "Good technical instincts, but answers stayed general: few "
                    "numbers and an unclear personal role."
                ),
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about a time you improved the reliability of a system.",
                        "We had issues with webhooks failing sometimes, so we looked "
                        "into it as a team and added some retries. I think it got a "
                        "lot better after that and customers complained less.",
                        48,
                        {
                            "API Design": None,
                            "Reliability": 3,
                            "Ownership": 2,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 4,
                        },
                        "The right story, told too briefly: no scale, no personal "
                        "role, and 'a lot better' instead of a result.",
                        "At Harborline I own the shipment-tracking API. Webhook "
                        "deliveries were failing [add how often], so I moved "
                        "delivery onto a queue with retries. Failures dropped to "
                        "[add the result you achieved].",
                        missing=[
                            {"point": "How often it failed", "covered": False},
                            {"point": "What you personally did", "covered": False},
                            {"point": "A measurable result", "covered": False},
                        ],
                        weak=[
                            {
                                "quote": "we looked into it as a team",
                                "why": "Hides what you did yourself.",
                            }
                        ],
                        star=star(r=False, note="No measurable result."),
                        tips=["Say 'I' for the parts you owned."],
                        strengths=["Picked a relevant, real reliability problem."],
                    ),
                    q(
                        "Technical",
                        "technical",
                        "How would you design an API endpoint that returns a "
                        "shipment's tracking history?",
                        "I'd do a GET on shipments slash id slash events, return the "
                        "events sorted by time, and paginate it. Maybe add caching.",
                        40,
                        {
                            "API Design": 3,
                            "Reliability": 2,
                            "Ownership": None,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 4,
                        },
                        "A sensible shape, but no detail on pagination, errors or "
                        "how caching stays correct.",
                        "I'd expose GET /shipments/{id}/events, newest first, with "
                        "cursor pagination so new events don't shift pages. A 404 "
                        "for unknown shipments, and a short cache keyed by the "
                        "latest event id so it never serves stale history.",
                        missing=[
                            {"point": "Pagination style", "covered": False},
                            {"point": "Error cases", "covered": False},
                            {"point": "Cache invalidation", "covered": False},
                        ],
                        tips=["Walk through one request end to end."],
                        strengths=["Chose a clean, resource-style URL."],
                    ),
                ],
            },
            {
                "days_ago": 1,
                "minutes": 10,
                "persona": "neutral",
                "takeaways": [
                    "Keep the numbers: they made this round much stronger.",
                    "Say what you'd do differently next time.",
                    "Tie technical choices to the customer impact.",
                ],
                "reason": (
                    "Clear improvement: specific numbers and a clear personal "
                    "role. Trade-offs could be explained more."
                ),
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about a time you improved the reliability of a system.",
                        "At Harborline I own the shipment-tracking API. About 3% of "
                        "webhook deliveries were failing. I moved delivery onto a "
                        "queue with exponential retries and a dead-letter queue, "
                        "and failures dropped to under 0.2% within a month.",
                        62,
                        {
                            "API Design": None,
                            "Reliability": 4,
                            "Ownership": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Specific and well structured, with a clear result.",
                        "At Harborline I own the shipment-tracking API. About 3% of "
                        "webhook deliveries were failing, so I moved delivery onto a "
                        "queue with exponential retries and a dead-letter queue. "
                        "Within a month failures were under 0.2%, and I added an "
                        "alert on the dead-letter queue so we'd catch new problems "
                        "early.",
                        missing=[
                            {"point": "A measurable result", "covered": True},
                            {"point": "What you'd do differently", "covered": False},
                        ],
                        star=star(),
                        tips=["Add one line on what you learned."],
                        strengths=["Clear numbers before and after."],
                    ),
                    q(
                        "Technical",
                        "technical",
                        "A query behind the tracking page got slow. How do you "
                        "find and fix it?",
                        "I'd check the slow query log and run EXPLAIN ANALYZE. Last "
                        "time it was a sequential scan on events by shipment id, so "
                        "I added a composite index on shipment id and created_at. "
                        "The p95 went from about 900 milliseconds to 40.",
                        55,
                        {
                            "API Design": None,
                            "Reliability": 4,
                            "Ownership": 3,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "A solid method backed by a real example.",
                        "I start from the slow query log and EXPLAIN ANALYZE. On "
                        "the tracking page it was a sequential scan on events, so I "
                        "added a composite index on (shipment_id, created_at), "
                        "checked write cost on staging, and p95 dropped from about "
                        "900 ms to 40 ms.",
                        missing=[
                            {"point": "Checking the write cost", "covered": False}
                        ],
                        star=star(),
                        tips=["Mention how you checked the fix didn't hurt writes."],
                        strengths=["Real before-and-after numbers."],
                    ),
                ],
            },
            {
                "days_ago": 0,
                "minutes": 30,
                "persona": "tough",
                "assignment": "done",
                "takeaways": [
                    "Interview-ready on reliability stories.",
                    "Keep design answers to two minutes.",
                    "Close with impact on customers.",
                ],
                "reason": (
                    "Strong, specific answers with clear ownership and results; "
                    "ready for a real mid-level loop."
                ),
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about a time you led an incident as on-call lead.",
                        "Last spring our event consumer fell behind by two hours "
                        "during a carrier outage. As on-call lead I paused the "
                        "non-urgent jobs, scaled the consumers from four to twelve, "
                        "and kept support updated every 30 minutes. We caught up in "
                        "40 minutes, and I wrote the post-mortem that added "
                        "autoscaling on queue depth.",
                        84,
                        {
                            "API Design": None,
                            "Reliability": 5,
                            "Ownership": 5,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 5,
                        },
                        "Excellent ownership and a clear result.",
                        "During a carrier outage last spring our event consumer "
                        "fell two hours behind. As on-call lead I paused non-urgent "
                        "jobs, scaled consumers from four to twelve and updated "
                        "support every 30 minutes. We caught up in 40 minutes, and "
                        "my post-mortem added autoscaling on queue depth, so it "
                        "hasn't happened since.",
                        missing=[{"point": "Lasting fix", "covered": True}],
                        star=star(),
                        strengths=[
                            "Took charge and communicated.",
                            "Followed up with a lasting fix.",
                        ],
                    ),
                    q(
                        "System design",
                        "system_design",
                        "Design a service that sends shipment status notifications "
                        "to customers.",
                        "Status changes go onto a queue. A notification worker "
                        "reads them, checks the customer's preferences, and sends "
                        "email or SMS through a provider, with retries and an "
                        "idempotency key so nobody gets the same message twice. I'd "
                        "track delivery rate and queue lag on a dashboard.",
                        96,
                        {
                            "API Design": 4,
                            "Reliability": 4,
                            "Ownership": None,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "A sound design with good reliability thinking.",
                        "Status changes are published to a queue. A notification "
                        "worker reads each one, checks the customer's preferences "
                        "and sends email or SMS through a provider, retrying with "
                        "an idempotency key so no one gets duplicates. I'd watch "
                        "delivery rate and queue lag, and add [add how you'd handle "
                        "a provider outage].",
                        missing=[{"point": "Provider outage plan", "covered": False}],
                        tips=["Say how you'd survive the provider going down."],
                        strengths=["Thought about duplicates and monitoring."],
                    ),
                    q(
                        "Collaboration",
                        "behavioral",
                        "How do you work with support when customers report bugs?",
                        "I set up a shared channel with support and a simple "
                        "template: shipment id, time, what they expected. That cut "
                        "the back-and-forth a lot, and I review new reports every "
                        "morning.",
                        45,
                        {
                            "API Design": None,
                            "Reliability": None,
                            "Ownership": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Practical and clear; one number would help.",
                        "I set up a shared channel with support and a short "
                        "template: shipment id, time, and what the customer "
                        "expected. It cut the back-and-forth by [add how much], "
                        "and I review new reports every morning.",
                        missing=[{"point": "A measurable result", "covered": False}],
                        star=star(r=False, note="The result is 'a lot'."),
                        strengths=["Made support's job easier."],
                    ),
                ],
            },
        ],
        "stories": [
            {
                "title": "Webhook failures from 3% to under 0.2%",
                "star": {
                    "situation": "Webhook deliveries on the tracking API failed about 3% of the time.",
                    "task": "Owner of the API; needed reliable delivery.",
                    "action": "Moved delivery to a queue with retries and a dead-letter queue.",
                    "result": "Failures under 0.2% within a month.",
                },
                "competencies": ["Reliability", "Ownership"],
                "strength": 4.3,
                "session": 1,
                "question": 0,
            },
            {
                "title": "Leading the carrier-outage incident",
                "star": {
                    "situation": "Event consumer fell two hours behind during an outage.",
                    "task": "On-call lead.",
                    "action": "Paused jobs, scaled consumers 4→12, updated support every 30 min.",
                    "result": "Caught up in 40 minutes; autoscaling added after.",
                },
                "competencies": ["Reliability", "Ownership"],
                "strength": 4.8,
                "session": 2,
                "question": 0,
            },
            {
                "title": "Tracking page query from 900 ms to 40 ms",
                "star": {
                    "situation": "The tracking page was slow.",
                    "task": "Find the cause.",
                    "action": "EXPLAIN ANALYZE, then a composite index.",
                    "result": "p95 from ~900 ms to 40 ms.",
                },
                "competencies": ["Reliability"],
                "strength": 4.0,
                "session": 1,
                "question": 1,
            },
            {
                "title": "Bug-report template with support",
                "star": {
                    "situation": "Bug reports from support lacked details.",
                    "task": None,
                    "action": "Shared channel and a short template; daily review.",
                    "result": None,
                },
                "competencies": ["Ownership"],
                "strength": 3.5,
                "session": 2,
                "question": 2,
            },
        ],
        "bank": [
            (
                0,
                1,
                "How would you design an API endpoint that returns a shipment's tracking history?",
                "API Design",
                -2,
            ),
            (
                2,
                1,
                "Design a service that sends shipment status notifications to customers.",
                "Reliability",
                -1,
            ),
        ],
        "assignments": [
            {
                "role": "Senior Backend Engineer (stretch role)",
                "minutes": 30,
                "due_in_days": 5,
                "jd": (
                    "Senior Backend Engineer: lead the design of high-volume event "
                    "APIs, mentor engineers, own reliability targets and drive "
                    "incident reviews."
                ),
            }
        ],
        "comment": (
            "Big step up from your first round, Alex. The incident story is your "
            "strongest: open with it in the real interview. Next, practise the "
            "provider-outage part of the design question."
        ),
    },
    # -------------------------------------------------------------- struggling
    {
        "key": "struggling",
        "name": "Jordan Reyes",
        "email": "jordan.reyes",
        "role": "Customer Success Manager",
        "seniority": "mid",
        # Rushes when nervous: the report's pace tip shows it.
        "wpm": 178,
        "licensed": False,
        "goal": 2,
        "resume": (
            "Jordan Reyes, Customer Success Specialist. 3 years at Brightdesk "
            "Software (fictional): manages 40 small-business accounts, runs "
            "onboarding calls, handles renewals with sales, built a FAQ for new "
            "customers."
        ),
        "jd": (
            "Customer Success Manager for mid-market accounts. Own renewals and "
            "expansion, reduce churn, run business reviews, and turn customer "
            "feedback into product requests."
        ),
        "rubric": [
            ("Account Management", "role", 0.4),
            ("Retention", "role", 0.35),
            ("Stakeholder Communication", "role", 0.25),
        ],
        "sessions": [
            {
                "days_ago": 16,
                "minutes": 10,
                "persona": "friendly",
                "takeaways": [
                    "Pick one specific customer story per question.",
                    "End every answer with what changed.",
                    "Cut the hedging ('I guess', 'kind of').",
                ],
                "reason": (
                    "Warm and well-meaning, but answers stayed general and "
                    "rarely reached a result."
                ),
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about a customer you kept from leaving.",
                        "I guess we just kind of looked at it as a team and tried to "
                        "make things better for them. It went fine in the end, they "
                        "stayed I think.",
                        28,
                        {
                            "Account Management": 2,
                            "Retention": 2,
                            "Stakeholder Communication": None,
                            "Structure": 2,
                            "Clarity": 2,
                            "Relevance": 3,
                        },
                        "No specific customer, action or result.",
                        "[Build this from your résumé: you manage 40 small-business "
                        "accounts. Pick one that was close to leaving: why, what "
                        "you did, and the result.]",
                        missing=[
                            {"point": "A specific customer", "covered": False},
                            {"point": "What you did", "covered": False},
                            {"point": "The outcome", "covered": False},
                        ],
                        weak=[
                            {
                                "quote": "I guess we just kind of looked at it as a team",
                                "why": "Vague, and hides your own role.",
                            }
                        ],
                        star=star(
                            t=False, a=False, r=False, note="Only a vague situation."
                        ),
                        tips=["Name the customer type and the risk."],
                    ),
                    q(
                        "Role skills",
                        "behavioral",
                        "How do you prepare for a business review with a customer?",
                        "I look at their account and see how things are going and "
                        "then we talk about it on the call.",
                        20,
                        {
                            "Account Management": 2,
                            "Retention": None,
                            "Stakeholder Communication": 2,
                            "Structure": 2,
                            "Clarity": 3,
                            "Relevance": 3,
                        },
                        "Too short to show a real process.",
                        "Before a review I pull [add the usage numbers you check], "
                        "list the customer's goals from onboarding, and prepare "
                        "two or three recommendations. On the call I [add how you "
                        "run it].",
                        missing=[
                            {"point": "Usage data", "covered": False},
                            {"point": "Customer goals", "covered": False},
                            {"point": "Recommendations", "covered": False},
                        ],
                        tips=["Walk through the steps in order."],
                    ),
                ],
            },
            {
                "days_ago": 10,
                "minutes": 10,
                "persona": "neutral",
                "takeaways": [
                    "Answer the question asked before adding context.",
                    "Use one number per story.",
                    "Practise out loud with a timer.",
                ],
                "reason": "Long answers drifted off the question; still no results.",
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about a customer you kept from leaving.",
                        "So there was this one customer, a bakery chain I think, and "
                        "they were unhappy with a lot of things, like the invoices "
                        "and the reports, and also our support was slow at the "
                        "time, and there was a new person on their side, so it was "
                        "complicated and we had a lot of calls.",
                        70,
                        {
                            "Account Management": 2,
                            "Retention": 2,
                            "Stakeholder Communication": 2,
                            "Structure": 2,
                            "Clarity": 2,
                            "Relevance": 2,
                        },
                        "Lots of background but no action or result.",
                        "A bakery-chain customer was close to cancelling over "
                        "invoicing errors and slow support. I [add the one thing you "
                        "did first], and [add the result: did they renew?].",
                        missing=[
                            {"point": "What you did", "covered": False},
                            {"point": "Did they renew", "covered": False},
                        ],
                        weak=[
                            {
                                "quote": "so it was complicated and we had a lot of calls",
                                "why": "Describes effort, not action or outcome.",
                            }
                        ],
                        star=star(t=False, a=False, r=False, note="Situation only."),
                        tips=["Spend 20% on the situation, 80% on what you did."],
                    ),
                    q(
                        "Role skills",
                        "behavioral",
                        "How do you turn customer feedback into product changes?",
                        "I tell the product team about it in Slack when customers "
                        "ask for things.",
                        15,
                        {
                            "Account Management": None,
                            "Retention": None,
                            "Stakeholder Communication": 2,
                            "Structure": 2,
                            "Clarity": 3,
                            "Relevance": 3,
                        },
                        "Too brief: no process or example.",
                        "I log each request with the customer's name and impact, "
                        "group similar ones, and bring the top [add how many] to "
                        "product each month. For example, [add one request that "
                        "shipped].",
                        missing=[
                            {"point": "A process", "covered": False},
                            {"point": "An example", "covered": False},
                        ],
                    ),
                ],
            },
            {
                "days_ago": 8,
                "minutes": 10,
                "persona": "friendly",
                "assignment": "done",
                "takeaways": [
                    "The FAQ story works: build two more like it.",
                    "Say the result as a number.",
                    "Practise the renewal question again.",
                ],
                "reason": (
                    "Some progress: one concrete example. Most answers still "
                    "lack a result."
                ),
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about something you built that helped customers.",
                        "New customers kept asking the same setup questions, so I "
                        "wrote a FAQ with screenshots and sent it after onboarding "
                        "calls. People seemed to like it and I got fewer of the "
                        "same tickets.",
                        42,
                        {
                            "Account Management": 3,
                            "Retention": 3,
                            "Stakeholder Communication": 3,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 4,
                        },
                        "A real example with a clear action; the result is vague.",
                        "New customers kept asking the same setup questions, so I "
                        "wrote an illustrated FAQ and sent it after every "
                        "onboarding call. Repeat setup tickets dropped by [add the "
                        "result you achieved].",
                        missing=[{"point": "A measurable result", "covered": False}],
                        star=star(r=False, note="'Fewer tickets' needs a number."),
                        strengths=["Spotted a pattern and fixed it."],
                    ),
                    q(
                        "Role skills",
                        "behavioral",
                        "Walk me through how you handle a renewal at risk.",
                        "I would talk to them and kind of see what the problem is "
                        "and maybe offer a discount or something.",
                        22,
                        {
                            "Account Management": 2,
                            "Retention": 2,
                            "Stakeholder Communication": 2,
                            "Structure": 2,
                            "Clarity": 2,
                            "Relevance": 3,
                        },
                        "A discount is the last resort; no diagnosis or plan.",
                        "I'd check their usage and support history first, then ask "
                        "the decision maker what success looks like. I'd agree a "
                        "short plan with [add the steps you'd take] and bring in "
                        "sales only if pricing is really the issue.",
                        missing=[
                            {"point": "Finding the root cause", "covered": False},
                            {"point": "A recovery plan", "covered": False},
                        ],
                        weak=[
                            {
                                "quote": "maybe offer a discount or something",
                                "why": "Sounds unplanned.",
                            }
                        ],
                    ),
                ],
            },
        ],
        "stories": [
            {
                "title": "Onboarding FAQ that cut repeat questions",
                "star": {
                    "situation": "New customers asked the same setup questions.",
                    "task": "Reduce repeat tickets.",
                    "action": "Wrote an illustrated FAQ sent after onboarding calls.",
                    "result": None,
                },
                "competencies": ["Account Management"],
                "strength": 3.0,
                "session": 2,
                "question": 0,
            },
            {
                "title": "Bakery chain close to cancelling",
                "star": {
                    "situation": "Unhappy over invoices, reports and slow support.",
                    "task": None,
                    "action": None,
                    "result": None,
                },
                "competencies": ["Retention"],
                "strength": 2.0,
                "session": 1,
                "question": 0,
            },
            {
                "title": "Passing feature requests to product",
                "star": {
                    "situation": "Customers asked for features.",
                    "task": None,
                    "action": "Shared requests with product in Slack.",
                    "result": None,
                },
                "competencies": ["Stakeholder Communication"],
                "strength": 2.0,
                "session": 1,
                "question": 1,
            },
        ],
        "bank": [
            (
                2,
                1,
                "Walk me through how you handle a renewal at risk.",
                "Retention",
                -3,
            ),
            (1, 0, "Tell me about a customer you kept from leaving.", "Retention", -2),
            (
                0,
                1,
                "How do you prepare for a business review with a customer?",
                "Account Management",
                -1,
            ),
        ],
        "assignments": [
            {
                "role": "Customer Success Manager (renewals focus)",
                "minutes": 10,
                "due_in_days": 3,
                "jd": (
                    "Customer Success Manager focused on renewals: run renewal "
                    "conversations, spot churn risk early, and work with sales on "
                    "pricing."
                ),
            }
        ],
        "comment": (
            "The FAQ story is a real win, Jordan: next time give it a number "
            "(how many fewer tickets?). For the renewal question, start with "
            "finding the cause before any discount. Let's practise that one."
        ),
    },
    # ---------------------------------------------------------------- others
    {
        "key": "analyst",
        "name": "Priya Natarajan",
        "email": "priya.natarajan",
        "role": "Data Analyst",
        "seniority": "entry",
        "licensed": False,
        "goal": 2,
        "resume": "Priya Natarajan, junior data analyst at Kestrel Retail (fictional). SQL, Python, dashboards for store managers.",
        "jd": "Data Analyst: build dashboards, write SQL, explain findings to non-technical teams.",
        "rubric": [("SQL", "role", 0.5), ("Communicating Insights", "role", 0.5)],
        "sessions": [
            {
                "days_ago": 12,
                "minutes": 10,
                "persona": "friendly",
                "takeaways": [
                    "Explain the 'so what' of each finding.",
                    "Name the decision it changed.",
                ],
                "reason": "Solid SQL, weaker at explaining impact.",
                "questions": [
                    q(
                        "Technical",
                        "technical",
                        "How would you find the top 5 stores by sales growth?",
                        "I'd sum sales per store per month, use a window function to compare to the previous month, and order by the growth.",
                        40,
                        {
                            "SQL": 4,
                            "Communicating Insights": None,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 4,
                        },
                        "Correct approach; edge cases not covered.",
                        "I'd sum monthly sales per store, use LAG() to get the previous month, compute growth, and take the top five, excluding stores open less than [add the cutoff you'd use] months.",
                        missing=[{"point": "New stores", "covered": False}],
                    ),
                    q(
                        "Behavioral",
                        "behavioral",
                        "Tell me about a time your analysis changed a decision.",
                        "I made a dashboard that showed some stores had too much stock and the managers used it.",
                        25,
                        {
                            "SQL": None,
                            "Communicating Insights": 2,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 3,
                        },
                        "The decision and its result are missing.",
                        "My stock dashboard showed [add which stores] were overstocked; managers cut orders by [add the result you achieved].",
                        star=star(r=False),
                    ),
                ],
            },
            {
                "days_ago": 3,
                "minutes": 10,
                "persona": "neutral",
                "takeaways": [
                    "Good progress on impact.",
                    "Keep answers under two minutes.",
                ],
                "reason": "Clearer impact and good SQL.",
                "questions": [
                    q(
                        "Behavioral",
                        "behavioral",
                        "Tell me about a time your analysis changed a decision.",
                        "My stock dashboard showed six stores were overstocked on seasonal items. Managers cut their next order by 20% and markdowns fell that quarter.",
                        45,
                        {
                            "SQL": None,
                            "Communicating Insights": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Specific and clear.",
                        "My stock dashboard showed six stores overstocked on seasonal items; managers cut the next order by 20% and markdowns fell that quarter.",
                        star=star(),
                    ),
                    q(
                        "Technical",
                        "technical",
                        "How do you check a dashboard's numbers are right?",
                        "I reconcile totals against the finance report and spot-check a few stores by hand.",
                        30,
                        {
                            "SQL": 3,
                            "Communicating Insights": 3,
                            "Structure": 3,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Good habits; could mention automated checks.",
                        "I reconcile totals with the finance report, spot-check a few stores, and [add an automated check you'd set up].",
                    ),
                ],
            },
        ],
    },
    {
        "key": "nurse",
        "name": "Sam Okafor",
        "email": "sam.okafor",
        "role": "Registered Nurse",
        "seniority": "mid",
        "licensed": True,
        "goal": 2,
        "resume": "Sam Okafor, RN, 5 years on a medical-surgical ward at Lakeside General (fictional). Charge nurse cover, preceptor for new graduates.",
        "jd": "Registered Nurse, medical-surgical unit: patient assessment, care planning, teamwork with doctors and families, calm under pressure.",
        "rubric": [("Patient Care", "role", 0.5), ("Teamwork", "role", 0.5)],
        "sessions": [
            {
                "days_ago": 11,
                "minutes": 10,
                "persona": "friendly",
                "takeaways": [
                    "Say what you assessed first.",
                    "Close with the patient outcome.",
                ],
                "reason": "Caring and safe; answers could be more structured.",
                "questions": [
                    q(
                        "Clinical judgment",
                        "scenario",
                        "Tell me about a time a patient's condition changed quickly.",
                        "A post-op patient's blood pressure dropped, so I called the doctor and we gave fluids and he was okay.",
                        35,
                        {
                            "Patient Care": 3,
                            "Teamwork": 3,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 4,
                        },
                        "Safe actions; the assessment steps are missing.",
                        "A post-op patient's blood pressure dropped to [add the reading]. I [add what you assessed first], escalated to the doctor using SBAR, and after fluids he stabilised.",
                        star=star(r=True, note="Assessment steps missing."),
                    ),
                    q(
                        "Teamwork",
                        "behavioral",
                        "How do you support a new graduate nurse?",
                        "I'm a preceptor, so I let them shadow me and then give them patients slowly.",
                        30,
                        {
                            "Patient Care": None,
                            "Teamwork": 4,
                            "Structure": 3,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Good approach; add how you give feedback.",
                        "As a preceptor I start new graduates shadowing, then hand over patients step by step, with [add how you give feedback].",
                    ),
                ],
            },
            {
                "days_ago": 4,
                "minutes": 10,
                "persona": "neutral",
                "takeaways": [
                    "Strong structure with SBAR.",
                    "Mention family communication.",
                ],
                "reason": "Clear, structured and safe.",
                "questions": [
                    q(
                        "Clinical judgment",
                        "scenario",
                        "Tell me about a time a patient's condition changed quickly.",
                        "A post-op patient's pressure fell to 85 over 50. I checked the wound and drains, repeated the obs, and called the doctor using SBAR. We gave a fluid bolus and he was stable within the hour.",
                        58,
                        {
                            "Patient Care": 4,
                            "Teamwork": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Clear assessment and escalation.",
                        "A post-op patient's pressure fell to 85/50. I checked the wound and drains, repeated observations and escalated with SBAR; after a fluid bolus he was stable within the hour.",
                        star=star(),
                    ),
                    q(
                        "Teamwork",
                        "behavioral",
                        "Tell me about a disagreement with a colleague.",
                        "A colleague wanted to delay a pain reassessment. I explained the policy and offered to do it myself, and we agreed.",
                        35,
                        {
                            "Patient Care": 3,
                            "Teamwork": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Calm and patient-focused.",
                        "A colleague wanted to delay a pain reassessment; I explained the policy, offered to do it myself, and we agreed on [add how you followed up].",
                    ),
                ],
            },
        ],
    },
    {
        "key": "marketing",
        "name": "Taylor Brooks",
        "email": "taylor.brooks",
        "role": "Marketing Coordinator",
        "seniority": "entry",
        "licensed": False,
        "goal": 3,
        "resume": "Taylor Brooks, marketing assistant at Fernway Outdoor (fictional): social posts, email newsletter, event support.",
        "jd": "Marketing Coordinator: run campaigns across email and social, track results, coordinate with design and sales.",
        "rubric": [
            ("Campaign Execution", "role", 0.5),
            ("Measuring Results", "role", 0.5),
        ],
        "sessions": [
            {
                "days_ago": 13,
                "minutes": 10,
                "persona": "friendly",
                "takeaways": [
                    "Name the metric you moved.",
                    "Describe your part clearly.",
                ],
                "reason": "Energetic, but results unclear.",
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about a campaign you ran.",
                        "I helped with the spring newsletter, made the images and wrote some of it. It did pretty well.",
                        28,
                        {
                            "Campaign Execution": 3,
                            "Measuring Results": 2,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 3,
                        },
                        "Your part and the result are vague.",
                        "I wrote and designed the spring newsletter for [add list size] subscribers; it reached an open rate of [add the result you achieved].",
                        star=star(r=False),
                    ),
                    q(
                        "Skills",
                        "behavioral",
                        "How do you decide what to post on social media?",
                        "I look at what competitors post and what's trending.",
                        18,
                        {
                            "Campaign Execution": 3,
                            "Measuring Results": 2,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 3,
                        },
                        "Missing your own data.",
                        "I check what performed best for us last month, look at [add the trends you watch], and plan posts around [add your goal].",
                    ),
                ],
            },
            {
                "days_ago": 5,
                "minutes": 10,
                "persona": "neutral",
                "takeaways": ["Better numbers.", "Talk about working with sales."],
                "reason": "Clearer results; collaboration still thin.",
                "questions": [
                    q(
                        "Experience",
                        "behavioral",
                        "Tell me about a campaign you ran.",
                        "I ran the spring newsletter for 12,000 subscribers. I tested two subject lines and the winner got a 31% open rate, up from 24%.",
                        40,
                        {
                            "Campaign Execution": 4,
                            "Measuring Results": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Specific and measurable.",
                        "I ran the spring newsletter for 12,000 subscribers, A/B tested subject lines, and lifted opens from 24% to 31%.",
                        star=star(),
                    ),
                    q(
                        "Skills",
                        "behavioral",
                        "How do you work with the sales team?",
                        "I send them the campaign calendar.",
                        12,
                        {
                            "Campaign Execution": 2,
                            "Measuring Results": None,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 3,
                        },
                        "Too short.",
                        "I share the campaign calendar with sales, ask what customers are asking about, and [add how you follow up on leads].",
                    ),
                ],
            },
        ],
    },
    {
        "key": "finance",
        "name": "Chris Lindqvist",
        "email": "chris.lindqvist",
        "role": "Financial Analyst",
        "seniority": "mid",
        "licensed": False,
        "goal": 2,
        "resume": "Chris Lindqvist, financial analyst at Ostra Manufacturing (fictional): monthly forecasts, variance analysis, Excel models.",
        "jd": "Financial Analyst: build forecasts, explain variances, support budgeting with department heads.",
        "rubric": [
            ("Financial Modeling", "role", 0.5),
            ("Business Partnering", "role", 0.5),
        ],
        "sessions": [
            {
                "days_ago": 15,
                "minutes": 10,
                "persona": "neutral",
                "takeaways": [
                    "Strong modelling answers.",
                    "Keep partnering stories concrete.",
                ],
                "reason": "Confident and specific.",
                "questions": [
                    q(
                        "Technical",
                        "technical",
                        "Walk me through how you build a monthly forecast.",
                        "I start from actuals, apply run-rates per cost centre, adjust for known events like price changes, and review it with each department head.",
                        50,
                        {
                            "Financial Modeling": 4,
                            "Business Partnering": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Clear, practical method.",
                        "I start from actuals, apply run-rates per cost centre, adjust for known events like price changes, and review with each department head.",
                    ),
                    q(
                        "Behavioral",
                        "behavioral",
                        "Tell me about a big variance you explained.",
                        "Freight costs were 18% over budget in Q3. I traced it to rush shipments from one supplier, and procurement renegotiated.",
                        45,
                        {
                            "Financial Modeling": 4,
                            "Business Partnering": 4,
                            "Structure": 4,
                            "Clarity": 4,
                            "Relevance": 4,
                        },
                        "Specific cause and action.",
                        "Q3 freight was 18% over budget; I traced it to rush shipments from one supplier and procurement renegotiated, saving [add the result you achieved].",
                        star=star(r=False),
                    ),
                ],
            },
            {
                "days_ago": 6,
                "minutes": 10,
                "persona": "tough",
                "takeaways": [
                    "Slow down under pressure.",
                    "Answer the question first.",
                ],
                "reason": "A dip under a tougher interviewer: rushed, less structured answers.",
                "questions": [
                    q(
                        "Behavioral",
                        "behavioral",
                        "Tell me about a time a department head disagreed with your numbers.",
                        "The operations head said my forecast was too low, and I mean, it was based on the data, so I kept it, but then later we changed it a bit.",
                        38,
                        {
                            "Financial Modeling": 3,
                            "Business Partnering": 2,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 4,
                        },
                        "Defensive; no clear resolution.",
                        "The operations head thought my forecast was too low. I walked through the drivers with them, added [add the input they gave], and we agreed a revised number.",
                        weak=[
                            {
                                "quote": "I mean, it was based on the data, so I kept it",
                                "why": "Sounds defensive.",
                            }
                        ],
                    ),
                    q(
                        "Technical",
                        "technical",
                        "How would you model the impact of a 5% price increase?",
                        "Revenue goes up 5% minus some volume loss, depending on elasticity.",
                        20,
                        {
                            "Financial Modeling": 3,
                            "Business Partnering": None,
                            "Structure": 3,
                            "Clarity": 3,
                            "Relevance": 4,
                        },
                        "Right idea; needs the steps.",
                        "I'd apply the 5% to price, estimate volume loss from [add the elasticity source], and show margin under a few scenarios.",
                    ),
                ],
            },
        ],
    },
]
