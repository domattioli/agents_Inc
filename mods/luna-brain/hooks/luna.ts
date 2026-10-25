import type { Register } from 'claude-code'

const AGENT = 'luna'
const AGENT_TYPES = ['luna-brain:luna', 'luna']
const HANDBACK = 'SubagentHandback'
const HANDBACK_ARGS = '{ message: string }'
const HANDBACK_CUE = 'call SubagentHandback('
const RESULT_CAP = 20_000
const DESC_CAP = 500
const MCP_DESC_CAP = 200
const RUN_TIMEOUT_MS = 300_000
const MODEL_LINE = /You are powered by the model|The exact model ID is/
const DELTA_HEADER =
  'New messages since your last reply. Same rules: reply with one JSON object {say, tools}; act on the latest messages; finish as the rules said. ' +
  'Request catalog tools in "tools", never through exec or another Codex tool.\n'
// luna sometimes reads Codex's read-only sandbox note as its own and answers that it cannot run a tool, calling none.
const REFUSAL = /(can['’]?t|cannot|unable to|not able to)\s+(run|read|inspect|execute|access|use|report)|tools?\b[^.]*\b(disabled|unavailable|not available)/i
const PUSH = 'You answered without running a tool the task needs. Every catalog tool is real and the host runs it for you; ' +
  'a value you report must come from a tool result in this conversation, never from a snapshot or a guess. ' +
  'Request the tools the task needs in "tools" now. Reply with exactly one JSON object.\n'
// A first reply that runs nothing is pushed once when it refuses a tool, or when the task names a catalog tool:
// luna answered "A=0" for `wc -l a.txt` without running Bash (Docker stress run, 2026-10-24).
export function skipsTools(reply: Reply | string | null, ranTool: boolean, task = '', names: readonly string[] = []): boolean {
  if (ranTool || reply === null || typeof reply === 'string' || reply.tools.length > 0) return false
  return REFUSAL.test(reply.say) || names.some(n => n !== HANDBACK && namesTool(task, n))
}
// A tool name counts only mid-sentence after a lowercase word ("with Bash", "then Read") or before "tool":
// "Write one Latin sentence" names no tool.
function namesTool(task: string, name: string): boolean {
  const n = name.replace(/[^\w]/g, '\\$&')
  return new RegExp(`(?<=[a-z,;:] )${n}\\b|\\b${n} tool\\b`).test(task)
}
// The task text: every user text block without harness reminders, which name tools the task never asked for.
export function taskText(messages: readonly Msg[]): string {
  return messages.filter(m => m.role === 'user').flatMap(m => m.content ?? []).filter(b => b.type === 'text')
    .map(b => String(b.text ?? '').replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, '')).join('\n')
}
const CORRECTION = (why: string) => `Your previous reply was rejected: ${why}. Reply with exactly one JSON object, only tools from the Tools list.\n`
const TOOL_TYPES_PATH = '.claude-plugin/types/claude-code-tools/index.d.ts'

const HEADER =
  'You drive an agent loop with real tools. To run a tool, name it in "tools"; the host runs it and its result arrives ' +
  'in the next step. Bash, Read and every other catalog tool work this way, so never answer that you cannot run one.\n' +
  'The catalog tools live in the host, not in Codex: they never appear in your own tool list, so never look for them there. ' +
  'Example, to run a shell command: {"say": "", "tools": [{"name": "Bash", "input": {"command": "ls"}}]}\n' +
  'You are luna (OpenAI GPT-6 Luna, model gpt-6-luna, run through Codex).\n' +
  'Codex\'s own tools (exec, wait, request_user_input, list_agents, send_message, collaboration.*, and any other) are ' +
  'not yours in this loop: never call them, never search them for a catalog tool, and never pass your reply to one. ' +
  'Your reply is the JSON object itself, written as your final message text. Every tool in the catalog below is real and available: call it ' +
  'by naming it in "tools", and its result arrives in the next step. Never report a catalog tool as unavailable.\n' +
  'Report only values you read in a tool result in this conversation; never guess one. The git status and other context ' +
  'in the system prompt is a snapshot from session start and may be stale: when the task asks for a command, run it.\n' +
  'A Read result starts each line with its line number and a tab: the last of those numbers is the line count.\n' +
  'Act on the latest messages; earlier ones are history.\n' +
  'Reply with exactly one JSON object and nothing else:\n' +
  '{"say": "<short text, may be empty>", "tools": [{"name": "<tool from the catalog>", "input": {...}}]}\n' +
  'Use "tools": [] only when you have nothing to call.\n'
const HANDBACK_RULES =
  'When the task is done, call SubagentHandback with your full report.\n' +
  'Call SubagentHandback alone, in a step after you have read the results it reports; never in the same step as another tool.\n'
// A background subagent on some builds has no SubagentHandback: its last plain reply is its report.
const FINAL_RULES =
  'When the task is done, reply with your full report in "say" and "tools": []. That reply ends your run.\n' +
  'There is no SubagentHandback tool here; never call it.\n'

const AGENT_PROMPT = 'You are a general-purpose agent. Complete the task you are given, then hand your report back.'

type Reply = { say: string; tools: { name: string; input: unknown }[] }
type Block = { type: string; [field: string]: unknown }
type Msg = { role: 'user' | 'assistant'; content: Block[] }
type Tool = { name: string; description: string; mcp?: boolean }
type Thinking = { kind: 'thinking'; index: number; text: string }
type Usage = { input_tokens: number; cached_input_tokens: number; output_tokens: number }
// One agents-inc run: the reply (or why it was rejected), whether the run itself failed, and what it cost.
type Outcome = { reply: Reply | string | null; failed: boolean }
// Per luna subagent: the Codex thread file it keeps, whether a run has used it, and how many api messages luna has seen.
type AgentState = { n: number; used: boolean; sent: number }

const lunaIds = new Set<string>()
const agents = new Map<string, AgentState>()
// Last running total Codex reported per thread file.
const threadTotals = new Map<string, Usage>()
const ZERO: Usage = { input_tokens: 0, cached_input_tokens: 0, output_tokens: 0 }
let sessionCwd = ''
let toolTypes: string | undefined // text of the engine-written built-in tool argument types, read once

type TurnUsageOut = {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
  model: string
}

// The system prompt names a placeholder Claude model; luna is not that model, so those lines go.
const stripModelLines = (text: string) => text.split('\n').filter(l => !MODEL_LINE.test(l)).join('\n')

// The harness's skill-listing reminder, cut to the skill names: luna can still call Skill by name, without ~25k chars
// of descriptions in every fresh prompt.
const SKILL_LIST = /(<system-reminder>\nThe following skills are available for use with the Skill tool:\n)([\s\S]*?)(<\/system-reminder>)/
export const trimSkillList = (text: string) =>
  text.replace(SKILL_LIST, (_, head: string, body: string, tail: string) => {
    const names = body.split('\n').map(l => /^- (\S+?)(?::\s|$)/.exec(l)?.[1]).filter(Boolean)
    return `${head}${names.join(', ')}\n${tail}`
  })

// The dir is git-ignored; agents-inc creates it. A fresh thread after a failed resume gets the suffix -2, -3...
const threadPath = (agentId: string, n: number) =>
  `${sessionCwd || '.'}/.scratch/luna-brain/${agentId.replace(/[^\w.-]/g, '_')}${n > 1 ? `-${n}` : ''}.thread`

const cap = (s: string, n: number) => (s.length > n ? `${s.slice(0, n)}\n[truncated ${s.length - n} chars]` : s)

// A field's `/** doc */` cut to its first sentence and FIELD_DOC_CAP chars; the field itself stays.
const FIELD_DOC_CAP = 160
const shortDoc = (line: string) =>
  line.replace(/\/\*\* (.*?) \*\//, (_, doc: string) => { const first = doc.split(/(?<=[.!?])\s/)[0]; return `/** ${first.length > FIELD_DOC_CAP ? `${first.slice(0, FIELD_DOC_CAP)}…` : first} */` })

// The stderr lines that explain a failed run: Codex's MCP start-up noise and the streamed progress lines left out.
const NOISE = /rmcp::|^agents-inc run: (event|usage|record) /
export const failureText = (stderr: string) =>
  stderr.split('\n').filter(l => l.trim() && !NOISE.test(l)).join('\n').slice(-600) || '(no other stderr)'

// The `Name: {...}` block of one tool in the BuiltinToolInputs interface; '' when the tool has none.
export function argBlock(types: string, name: string): string {
  const lines = types.split('\n')
  const start = lines.findIndex(l => l.startsWith(`    ${name}: {`))
  if (start < 0) return ''
  if (lines[start].trimEnd().endsWith('{}')) return lines[start].trim()
  const end = lines.findIndex((l, i) => i > start && l === '    }')
  return end < 0 ? '' : lines.slice(start, end + 1).map(l => shortDoc(l.slice(4))).join('\n')
}

export function catalog(tools: readonly Tool[], types: string, hand = true): string {
  const entries = tools.map(t => {
    const block = argBlock(types, t.name)
    const description = t.mcp ? cap(t.description.split(/(?<=[.!?])\s/)[0], MCP_DESC_CAP) : cap(t.description, DESC_CAP)
    return `- ${t.name}: ${description}${block ? `\n  Arguments:\n${block.replace(/^/gm, '  ')}` : ''}`
  })
  if (hand) entries.push(`- ${HANDBACK}: Deliver your final report and end your run.\n  Arguments: ${HANDBACK_ARGS}`)
  return entries.join('\n')
}

function resultText(content: unknown): string {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return content === undefined ? '' : JSON.stringify(content)
  return content.map(b => (b && typeof b === 'object' && typeof (b as Block).text === 'string' ? (b as Block).text : `[${(b as Block)?.type ?? 'block'}]`)).join('\n')
}

// Every message in order, every block kept: text as written, calls as name + JSON, results capped.
export function render(messages: readonly Msg[]): string {
  const out: string[] = []
  const toolNames = new Map<unknown, string>()
  for (const m of messages) {
    for (const b of m.content ?? []) {
      if (b.type === 'text') out.push(`${m.role}: ${trimSkillList(stripModelLines(String(b.text ?? '')))}`)
      else if (b.type === 'tool_use') {
        toolNames.set(b.id, String(b.name))
        out.push(`assistant tool call: ${String(b.name)} ${JSON.stringify(b.input ?? {})}`)
      } else if (b.type === 'tool_result') {
        let text = resultText(b.content)
        // Read numbers the empty line after a file's final newline: luna counted 96 lines in a 95-line file.
        // The harness may append reminders after the file text, so the empty line is found before them.
        if (toolNames.get(b.tool_use_id) === 'Read') text = text.replace(/\n[ \t]*\d+\t?[ \t]*(?=(\n*<system-reminder>[\s\S]*)?$)/, '')
        out.push(`tool result${b.is_error ? ' (error)' : ''}: ${cap(text, RESULT_CAP)}`)
      }
      else out.push(`${m.role}: [${b.type}]`)
    }
  }
  return out.join('\n')
}

export function buildPrompt(system: string, tools: string, messages: readonly Msg[], hand = true): string {
  return `${HEADER}${hand ? HANDBACK_RULES : FINAL_RULES}\nSystem prompt:\n${system}\n\nTools:\n${tools}\n\nConversation:\n${render(messages) || '(empty)'}\n`
}

// First balanced {...} in the text, parsed; a reason string when none parses or the shape is wrong.
// luna may write a tool request as one message and, with no Codex tool to run it, go on to a final message that guesses
// the results ("B=1" for `wc -l b.txt`; Docker stress run, 2026-10-25). The first message that requests tools ends the step.
export function pickReply(messages: readonly string[], stdout: string, allowed?: ReadonlySet<string>): Reply | string {
  for (const text of messages) {
    const r = parseReply(text, allowed)
    if (typeof r !== 'string' && r.tools.length > 0) return r
  }
  return parseReply(stdout, allowed)
}

export function parseReply(stdout: string, allowed?: ReadonlySet<string>): Reply | string {
  for (let start = stdout.indexOf('{'); start >= 0; start = stdout.indexOf('{', start + 1)) {
    let depth = 0
    let inStr = false
    for (let i = start; i < stdout.length; i++) {
      const c = stdout[i]
      if (inStr) {
        if (c === '\\') i++
        else if (c === '"') inStr = false
      } else if (c === '"') inStr = true
      else if (c === '{') depth++
      else if (c === '}' && --depth === 0) {
        let obj: unknown
        try {
          obj = JSON.parse(stdout.slice(start, i + 1))
        } catch {
          break
        }
        return shape(obj, allowed)
      }
    }
  }
  return 'no JSON object in the reply'
}

function shape(obj: unknown, allowed?: ReadonlySet<string>): Reply | string {
  if (typeof obj !== 'object' || obj === null) return 'reply is not an object'
  const o = obj as { say?: unknown; tools?: unknown }
  const tools = o.tools === undefined ? [] : o.tools
  if (!Array.isArray(tools)) return '"tools" is not a list'
  const list: Reply['tools'] = []
  for (const t of tools) {
    const name = (t as { name?: unknown } | null)?.name
    if (typeof name !== 'string' || (allowed && !allowed.has(name))) return `unknown tool ${JSON.stringify(name)}; use only a tool name from the Tools list`
    list.push({ name, input: (t as { input?: unknown }).input ?? {} })
  }
  return { say: typeof o.say === 'string' ? o.say : '', tools: list }
}

// Where the harness offers SubagentHandback, plain final text is ignored: the report has to travel through it.
export function handback(out: Reply, hand = true): Reply {
  if (!hand) return out
  // A hand-back next to other calls would report before their results exist: drop it, the next step can hand back.
  const others = out.tools.filter(t => t.name !== HANDBACK)
  if (others.length > 0 && others.length < out.tools.length) return { ...out, tools: others }
  return out.tools.length === 0 && out.say ? { say: out.say, tools: [{ name: HANDBACK, input: { message: out.say } }] } : out
}

async function readToolTypes($: { plugin: { root: string }; fs: { read: (p: string) => Promise<unknown> } }): Promise<string> {
  if (toolTypes !== undefined) return toolTypes
  try {
    const text = await $.fs.read(`${$.plugin.root}/${TOOL_TYPES_PATH}`)
    if (typeof text === 'string') return (toolTypes = text)
  } catch {
    // missing file: descriptions only
  }
  return ''
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    sessionCwd = e.cwd
    // No tools and no permissionMode: the agent inherits the parent's, like any native subagent.
    await $.agent.register({
      name: AGENT,
      description: 'General-purpose agent whose reasoning is done by luna (Codex). Spike; use only when asked for luna.',
      prompt: AGENT_PROMPT,
      model: 'haiku', // placeholder: turn.step never calls it for this agent
    })
    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    const r = await next(e)
    if (AGENT_TYPES.includes(e.subagentType) && r.agentId) lunaIds.add(r.agentId)
    return r
  })

  on('turn.step', async function* ($, e, next) {
    const id = e.agentId
    if (id === undefined) return yield* next(e)
    if (!lunaIds.has(id)) {
      // The spawn hook may not have recorded the id yet; the agent list knows the type.
      const known = await $.agent.list().then(l => l.some(a => a.id === id && AGENT_TYPES.includes(a.type))).catch(() => false)
      if (!known) return yield* next(e)
      lunaIds.add(id)
    }

    const t0 = await $.clock.now()
    // Shown live, not recorded: the window has something to show while luna works.
    yield { kind: 'thinking', index: 0, text: `luna is working on step ${e.index}…` }
    const aborted = new Promise<null>(res => {
      if (next.signal.aborted) res(null)
      else next.signal.addEventListener('abort', () => res(null), { once: true })
    })

    const acc: { usage: Usage | null; slug?: string } = { usage: null } // summed over this step's runs
    const STOP = Symbol('stop')

    // One run: stderr progress lines become thinking chunks as they arrive; stdout is the reply.
    const ask = async function* (prompt: string, thread: string, allowed: ReadonlySet<string>): AsyncGenerator<Thinking, Outcome> {
      const timer = new AbortController()
      const stop = Promise.race([
        aborted.then(() => STOP),
        $.clock.sleep(RUN_TIMEOUT_MS, { signal: timer.signal }).then(() => STOP, () => new Promise<never>(() => {})),
      ])
      const stream = $.process.spawn({
        argv: ['agents-inc', 'run', '--model', 'luna', '--effort', 'low', '--no-tools', '--host-tools', '--cwd', sessionCwd, '--thread', thread],
        cwd: sessionCwd || undefined,
        input: prompt,
      })
      let stdout = ''
      let stderr = ''
      let pending = ''
      const lines: string[] = []
      const said: string[] = [] // agent_message texts, in order
      const take = (line: string) => {
        const m = /^agents-inc run: (event|usage|record) (.*)$/.exec(line)
        if (!m) return
        let data: Record<string, unknown>
        try {
          data = JSON.parse(m[2])
        } catch {
          return
        }
        if (m[1] === 'record' && typeof data.slug === 'string') acc.slug = data.slug
        else if (m[1] === 'usage') {
          // Codex reports the thread's running total: this run's share is the rise since the last report.
          const total: Usage = {
            input_tokens: Number(data.input_tokens) || 0,
            cached_input_tokens: Number(data.cached_input_tokens) || 0,
            output_tokens: Number(data.output_tokens) || 0,
          }
          const before = threadTotals.get(thread) ?? ZERO
          threadTotals.set(thread, total)
          const u = acc.usage ?? ZERO
          acc.usage = {
            input_tokens: u.input_tokens + Math.max(0, total.input_tokens - before.input_tokens),
            cached_input_tokens: u.cached_input_tokens + Math.max(0, total.cached_input_tokens - before.cached_input_tokens),
            output_tokens: u.output_tokens + Math.max(0, total.output_tokens - before.output_tokens),
          }
        } else if (m[1] === 'event' && typeof data.text === 'string') {
          lines.push(data.text)
          if (data.kind === 'agent_message') said.push(data.text)
        }
      }
      const feed = (text: string) => {
        pending += text
        const parts = pending.split('\n')
        pending = parts.pop() ?? ''
        parts.forEach(take)
      }
      try {
        for (;;) {
          const n = await Promise.race([stream.next(), stop])
          if (n === STOP) {
            void stream.return(undefined as never).catch(() => {})
            return { reply: next.signal.aborted ? null : 'agents-inc run timed out', failed: !next.signal.aborted }
          }
          if (n.done) {
            if (pending) take(pending)
            for (const text of lines.splice(0)) yield { kind: 'thinking', index: 0, text }
            if (n.value.code === 0) return { reply: pickReply(said, stdout, allowed), failed: false }
            const why = `agents-inc run exited ${n.value.code ?? n.value.signal}, stdout ${stdout.length} chars: ${failureText(stderr)}`
            $.ui.log(`luna-brain: ${why}`, { to: 'debug' })
            return { reply: why, failed: true }
          }
          if (n.value.stream === 'stdout') stdout += n.value.text
          else {
            stderr += n.value.text
            feed(n.value.text)
            for (const text of lines.splice(0)) yield { kind: 'thinking', index: 0, text }
          }
        }
      } catch (err) {
        return { reply: `agents-inc run failed: ${String((err as Error)?.message ?? err)}`, failed: true }
      } finally {
        timer.abort()
      }
    }

    const tools: Tool[] = await $.tool.list().catch(() => [])
    const api = await $.session.messages({ agentId: id, as: 'api' }).catch(() => [])
    const messages = Array.isArray(api) ? (api as Msg[]) : []
    // The harness announces SubagentHandback in a reminder when it serves it; a background agent on some builds has none
    // and loops on "No such tool available" if told to call it (Linux, Claude Code 2.1.310, 2026-10-24).
    const hand = tools.some(t => t.name === HANDBACK) || JSON.stringify(messages).includes(HANDBACK_CUE)
    const names = [...tools.filter(t => t.name !== HANDBACK).map(t => t.name), ...(hand ? [HANDBACK] : [])]
    const allowed = new Set(names)
    const composed = await $.prompt.compose({ tools: names }).catch(() => ({ sections: [] }))
    const system = [...composed.sections.map(s => stripModelLines(s.text)), AGENT_PROMPT].join('\n\n')
    const types = await readToolTypes($)
    const full = () => buildPrompt(system, catalog(tools, types, hand), messages, hand)

    const st = agents.get(id) ?? { n: 1, used: false, sent: 0 }
    agents.set(id, st)
    // A compacted conversation holds fewer messages than luna has seen: the thread no longer matches it, so start over.
    if (st.used && messages.length < st.sent) Object.assign(st, { n: st.n + 1, used: false, sent: 0 })
    let resumed = st.used
    const sentBefore = st.sent
    let prompt = resumed ? `${DELTA_HEADER}${render(messages.slice(st.sent)) || '(nothing new)'}\n` : full()
    let chars = prompt.length
    // Spike: keep the last fresh prompt beside the thread file, to see what fills it.
    if (!resumed) await $.fs.write(`${threadPath(id, st.n)}.prompt.txt`, prompt).catch(() => undefined)
    let run = yield* ask(prompt, threadPath(id, st.n), allowed)
    if (run.failed) {
      // A thread that failed may be half-written: start another one with the whole conversation.
      st.n++
      st.used = false
      resumed = false
      prompt = full()
      chars += prompt.length
      run = yield* ask(prompt, threadPath(id, st.n), allowed)
    } else if (typeof run.reply === 'string') {
      // The thread already holds the prompt: the correction alone is enough.
      prompt = CORRECTION(run.reply)
      chars += prompt.length
      run = yield* ask(prompt, threadPath(id, st.n), allowed)
    }
    if (!run.failed && skipsTools(run.reply, JSON.stringify(messages).includes('"tool_result"'), taskText(messages), names)) {
      // One push; a second reply without tools stands as luna's answer.
      prompt = PUSH
      chars += prompt.length
      const again = yield* ask(prompt, threadPath(id, st.n), allowed)
      // An empty pushed reply keeps the first one: luna once answered the push with {"say": "", "tools": []}.
      if (!again.failed && again.reply !== null && typeof again.reply !== 'string' && (again.reply.tools.length > 0 || again.reply.say)) run = again
    }
    if (!run.failed) st.used = true
    const reply = run.reply
    if (typeof reply !== 'string' && reply !== null) st.sent = messages.length
    const ms = (await $.clock.now()) - t0
    $.ui.log(`luna-brain: step ${e.index} of ${id} took ${ms} ms, prompt ${chars} chars, ${resumed ? 'resumed' : 'fresh'} thread, system ${system.length} catalog ${catalog(tools, types, hand).length} conversation ${render(messages).length} chars, ${names.length} tools, handback ${hand ? 'on' : 'off'}, messages ${messages.length} sent ${sentBefore}`, { to: 'debug' })
    const tokens = acc.usage
    const turnUsage: TurnUsageOut | null = tokens
      ? {
          input_tokens: tokens.input_tokens - tokens.cached_input_tokens,
          output_tokens: tokens.output_tokens,
          cache_read_input_tokens: tokens.cached_input_tokens,
          cache_creation_input_tokens: 0,
          model: acc.slug ?? 'luna',
        }
      : null

    if (reply === null) return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: null, usage: turnUsage }

    const out: Reply = typeof reply === 'string' ? { say: 'luna reply unparsable', tools: [] } : handback(reply, hand)
    let index = 1 // block 0 is the live thinking line
    if (out.say) yield { kind: 'text', index: index++, text: out.say }
    for (const [n, tool] of out.tools.entries()) {
      yield { kind: 'tool', index, id: `luna_${e.turnId}_${e.index}_${n}`, name: tool.name }
      yield { kind: 'input', index, json: JSON.stringify(tool.input) }
      index++
    }
    const stopReason = out.tools.length > 0 ? 'tool_use' : 'end_turn'
    yield { kind: 'stop', stopReason, usage: turnUsage }
    return { turnId: e.turnId, index: e.index, answer: out.say, toolUses: out.tools, stopReason, usage: turnUsage }
  })
}
