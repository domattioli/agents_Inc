# Start here

- Reader
  - **Audience**
    - This page is for someone who has not run the system before.
  - **Style**
    - It uses plain language because the other docs are compressed for experienced readers.
  - **Next reading**
    - Return to those docs after this page.

## What this is

- Delegation system
  - **Purpose**
    - It gets several AI models to do work cheaply without trusting any model blindly.
  - **Division of labor**
    - A capable model supervises while cheaper models handle narrow jobs such as reading a long document, extracting every date from files, or writing a first draft.
  - **Core problem**
    - The difficult part is deciding whether the returned work is correct.

## The two pieces

- System
  - **Plumbing**
    - `skills/codex-bridge/` sends requests to OpenAI, Google, or Mistral, retries temporary failures, stops on exhausted free requests, and records cost.
  - **Judgment**
    - `skills/workerbee/` contains no code. It defines model choice and work verification.
  - **Boundary**
    - Separate layers let you replace the plumbing while keeping the supervision lessons.

## The one rule

- Independent checking
  - **Failure mode**
    - An AI model can report what it meant to produce instead of what it produced.
  - **Evidence**
    - That happened three times in a row during one session on this machine, and each report looked convincing.
  - **Rule**
    - The thing that checks the work must not be the thing that did the work.
  - **Practice**
    - Write the check yourself or have the supervising model write it somewhere the worker cannot edit, then run it yourself.
  - **Reason**
    - A self-reported result is not evidence.

## What it costs

- Billing
  - **Anthropic subscription**
    - This covers Claude models.
  - **ChatGPT subscription**
    - This covers OpenAI models.
  - **API keys**
    - Google’s free tier, Mistral, and OpenRouter use pay-per-use access.
  - **Budget mode**
    - It shifts work from the first bill to the second and third, which can save money while increasing verification time.
  - **Constraint**
    - Use it when money limits the work, not when correctness limits it.
  - **Price rule**
    - Unknown price and free price are different facts.
  - **Evidence**
    - Treating an unknown price as free once inflated a savings figure by a factor of twenty-nine.

## If you are a lawyer

- Confidentiality
  - **Transmission**
    - Sending text to a cloud AI model sends that text to the company’s servers.
  - **Privilege**
    - Summarizing a privileged document still transmits the privileged document.
  - **Decision**
    - Decide what may leave the machine, write the rule as an absolute rule, and include it in every model instruction.
  - **Scope**
    - Client names, case facts, and active matter files require your decision and your bar’s decision.
- Hard stops
  - **Client communications**
    - Do not delegate anything filed, served, or sent to a client. You are the signatory.
  - **High-cost errors**
    - Do not delegate work where confident error is worse than delay.
- Verification
  - **Problem**
    - Law has no compiler, so fluent wrong prose is harder to catch than faulty code.
  - **Gate**
    - Define how you will know a category of work is wrong before delegating it.
  - **Test set**
    - Keep twenty documents you handled correctly, run every new delegation against them, and count misses.

## Actually running something

- Prerequisite
  - **Access**
    - You need the `codex` command-line tool logged into ChatGPT, a Google Gemini API key, or a Mistral API key.
  - **First job**
    - Put a key in place before using the simplest example.

```bash
skills/codex-bridge/scripts/agent.sh submit --backend gemini --wait "your question here"
```

`agent.sh list` shows past jobs. `agent.sh result <id>` reprints one.

- Key handling
  - **Location**
    - Keys live in a file.
  - **Prohibition**
    - Never type a key into a command or paste it into a model message.
  - **Exposure**
    - If a real key enters a chat window, treat it as compromised and replace it.

## When you are ready

- Further reading
  - **System**
    - `HOW-IT-WORKS.md` describes the whole system in compressed form.
  - **Extension**
    - `EXTENDING.md` covers new models, vendors, and domains, including a law-practice example.
  - **Discipline**
    - `../skills/workerbee/SKILL.md` contains the full supervision rules and their failure history.
  - **Style**
    - These documents use terse shorthand for experienced readers. That is intentional.
