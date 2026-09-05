# Start here

For someone who has not run this before. Plain language on purpose — the other two docs in this folder are written in a compressed shorthand for people who already know the system, and they will not make sense yet. Come back to them later.

## What this is

A way to get several different AI models to do work for you, cheaply, without trusting any of them blindly.

The idea is simple. Good AI models are expensive. Cheap ones are often good enough for a specific narrow job — reading a long document, pulling every date out of a pile of files, writing a first draft. So you use one capable model as a supervisor, and it hands the grunt work to cheaper ones.

The hard part is not the handing off. It is knowing whether to believe what comes back. Most of this repo exists for that second problem.

## The two pieces

**`skills/codex-bridge/`** is the plumbing. It knows how to send a request to OpenAI, Google, or Mistral, how to retry when one is briefly down, how to stop when one has run out of free requests, and how to record what everything cost.

**`skills/workerbee/`** is the judgment. It has no code in it at all. It is a written set of rules about which model to use for which job, and — mostly — how to check the work.

Keeping these separate is deliberate. You can swap out the plumbing without losing the lessons, and the lessons are the expensive part.

## The one thing to understand before anything else

An AI model will tell you it succeeded when it did not.

Not because it is lying. Because when you ask it to do a task and report whether it worked, it tends to report what it *meant* to produce rather than what it actually produced. In one session on this machine that happened three separate times in a row, and each report looked completely convincing.

So the rule is: **the thing that checks the work must not be the thing that did the work.** You write the check, or the supervising model does, and it lives somewhere the worker cannot touch. When a model says "done, all tests pass," you run the tests yourself. It takes ten seconds and it is the difference between this being useful and this being dangerous.

If you remember nothing else from this document, remember that paragraph.

## What it costs

Three separate bills, and they do not mix:

- Your Anthropic subscription (the Claude models)
- Your ChatGPT subscription (the OpenAI models)
- Pay-per-use API keys (Google's free tier, Mistral, OpenRouter)

"Budget mode" means pushing work off the first bill onto the second and third. It genuinely saves money. It also costs you more time checking results, because you cannot see what an outside model read before it answered. That is a real trade, not a free win. Use it when money is the constraint, not when being right is the constraint.

One specific warning, because it has already caused a bad number here: if you build any kind of cost report, never treat "I don't know this model's price" as "this model is free." Those are different facts. Merging them once inflated a savings figure by a factor of twenty-nine.

## If you are a lawyer, read this part twice

Everything below is about your obligations, not about the software.

**Sending text to a cloud AI model means that text leaves your computer.** It goes to a company's servers. Summarizing a privileged document is still transmitting a privileged document. The fact that you only asked for a summary does not change what you sent.

Before you wire any of this up to real matter files, decide — and write down — what is allowed to leave the machine. Client names? Case facts? Nothing at all from an active matter? That is your call and your bar's call, not this repo's. Write it as an absolute rule, not an intention, and put it in the instructions you give the model every single time. Models do not remember your preferences between sessions.

Two things should probably never be delegated regardless of how well this works for you:

1. Anything that gets filed, served, or sent to a client. You are the signatory. A first draft is a first draft.
2. Anything where being confidently wrong is worse than being slow.

And the genuinely unsolved problem: in software you can check a model's work by running tests. Law has no compiler. Fluent, confident, wrong output is the failure mode you should expect, and it is much harder to catch in prose than in code. Before you delegate a category of work, figure out how you would *know* it came back wrong. If you cannot answer that, do not delegate that category yet.

The best available substitute is boring and it works: take twenty documents you have already handled correctly, keep them as a permanent test set, and every time you set up a new delegation, run it against those twenty first and count what it missed.

## Actually running something

You need at least one of: the `codex` command-line tool logged into a ChatGPT account, a Google Gemini API key, or a Mistral API key.

The simplest possible use, once a key is in place:

```bash
skills/codex-bridge/scripts/agent.sh submit --backend gemini --wait "your question here"
```

That queues one job, waits for it, and prints the answer. `agent.sh list` shows past jobs; `agent.sh result <id>` reprints one.

Keys live in a file, never typed into a command and never pasted into a message to a model. If you ever paste a real key into a chat window, treat it as compromised and get a new one.

## When you are ready for more

- `HOW-IT-WORKS.md` — the whole system, compressed
- `EXTENDING.md` — adding a new model or vendor, and a worked example of adapting this to a law practice
- `../skills/workerbee/SKILL.md` — the full supervision discipline, including every mistake that produced these rules

Those three are written in a terse shorthand. That is intentional and it is not you — they are aimed at readers who have already done this a few times.
