# Demo script

About five minutes. Every number you quote should be read off the screen at the time; this script
deliberately contains none that could go stale.

> "Here's what's real. Here's what's roadmap. We chose honesty over hype. This is what a real
> 30-hour build looks like."

## Before you start

```bash
# terminal 1, in backend/
.venv/Scripts/activate
uvicorn app.main:app --port 8000

# terminal 2, in the project root
npm run dev            # http://localhost:3000
```

Sign in with the demo role picker as **SIU Investigator**. Keep a second browser profile signed in
as **Viewer** if you want to show role limits.

## 1. Open on the banner (15 seconds)

Point at the strip at the top of every screen: *Synthetic demo. Not a fraud determination.*

> "Everything you'll see is synthetic. And nothing this system produces is a fraud finding. It
> produces a ranked list of things a person should look at, with the evidence attached."

## 2. Dashboard: the funnel (40 seconds)

> "These are real counts from our backend, not a mock. Claims come in, a fraction raise an alert,
> alerts cluster into cases by provider, and the queue picks the cases that fit the team's hours."

Read the four funnel numbers aloud. Say what they are counts of.

## 3. Inject a test scheme (60 seconds)

Demo, then **Inject a test scheme**. Press **Referral ring**.

> "That just sent a dozen synthetic claims through the real pipeline: coverage rules, eleven
> billing rules, the model, the referral graph. It tells you which detectors flagged it and how
> long the last claim took."

Press two or three more. All eight open a case. Say why:

> "A case opens on any of three conditions: the combined risk score, a single near-certain rule
> finding, or high suspicion with strong evidence. Opening a case only asks a person to look."

## 4. Case detail: evidence and limits (75 seconds)

Click **View case**. Go to **Evidence**.

> "Each finding says what triggered it, which claim and which fields it came from. And at the
> bottom, what the system does not know. We print the limitations on every case."

Open **Counterfactual**:

> "These are recomputed, not written. Remove a finding, re-score, show the new number."

Open **Overview** and point at **Similar cases** and the model warning:

> "Similar earlier claims from other providers, by TF-IDF over codes and findings. No PyTorch.
> And this label: the model is trained on synthetic data and is not validated for production."

## 5. A person decides (45 seconds)

**Decision** tab. Choose an outcome, type a reason, record it.

> "Notes are required. The decision becomes an audit entry and a training label. Nothing is sent
> to the claims system, no one is denied, no provider is notified."

Scroll to the audit trail under the form: the views, the brief, the decision, with your staff ID.

Switch to the Viewer profile and show the same tab: it can read, it cannot decide.

## 6. Coverage is not fraud (30 seconds)

**Claims** screen. Point at the coverage column and the banner.

> "Coverage is checked first. A claim that fails coverage gets no fraud score at all. It goes to
> claims staff, and it is never called fraud or a denial."

## 7. What is not real yet (60 seconds). Say this part plainly.

Open **Settings**, **Coverage rules**:

> "Our coverage rules are illustrative. We wrote them for the demo. The authoritative IRDAI rule
> set is not loaded, and the screen says so: zero of seventy-eight. We built the import path and
> refused to invent the rules."

Open **Models**:

> "The headline accuracy is flattering because the data is synthetic and the patterns are easy.
> So we also test on providers the model has never seen and we publish that number next to it.
> Fairness across provider and member groups: not yet measured."

Open **Admin**, **System health**:

> "Today we're on SQLite for the demo, one claim at a time. Here is the measured latency. The
> architecture supports Postgres with multiple workers. That's a config change, not a rewrite.
> But we have not measured it, so we are not going to quote you a number for it."

Brief tab, toggle **Template + LLM enhancement**:

> "Briefs are templates over stored evidence, so every line traces back. The LLM layer is opt-in,
> every line it writes must cite its evidence, and anything with a number that isn't in the
> evidence is thrown away. Without an API key it says so and shows the template version."

## 8. Close (15 seconds)

> "What's real: ingestion, eleven rules, a model, a referral graph, capacity-aware queue, an audit
> trail that can't be edited, strict tenant isolation, and a frontend wired to all of it.
> What's roadmap: authoritative rules, real training data, a fairness audit, and scale testing.
> We'd rather show you a smaller thing that is true."

## If something goes wrong

| Symptom | Likely cause | What to say and do |
|---|---|---|
| Screens show "could not be loaded" and mention the backend | Backend not running | Start `uvicorn`; press **Try again** |
| First inject takes a few seconds | Model loading on first use | "First call loads the model"; press another |
| Enhancement says "not configured" | No `OLLAMA_API_KEY` | That is the designed fallback; show it as such |
| Map tiles missing | No internet | Use the list beside the map; it has the same data |
