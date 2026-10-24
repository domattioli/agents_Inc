import type { Register } from 'claude-code'

const AGENT = 'luna'
const AGENT_TYPES = ['luna-brain:luna', 'luna']
const HANDBACK = 'SubagentHandback'
const HANDBACK_ARGS = '{ message: string }'
const RESULT_CAP = 20_000
const DESC_CAP = 1_200
const MCP_DESC_CAP = 200
const RUN_TIMEOUT_MS = 300_000
const MODEL_LINE = /You are powered by the model|The exact model ID is/
const DELTA_HEADER =
  'New messages since your last reply. Same rules: reply with one JSON object {say, tools}; act on the latest messages; hand back alone when done.\n'
const CORRECTION = (why: string) => `Your previous reply was rejected: ${why}. Reply with exactly one JSON object, only tools from the Tools list.\n`
const TOOL_TYPES_PATH = '.claude-plugin/types/claude-code-tools/index.d.ts'

const HEADER =
  'You are the reasoning step of an agent loop. You cannot run tools yourself. The host runs the tools you name.\n' +
  'You are luna (OpenAI GPT-5.6 Luna, run through Codex).\n' +
  'Your own Codex tools are off on purpose. Every tool in the catalog below is real and available: call it by naming it ' +
  'in "tools", and its result arrives in the next step. Never report a catalog tool as unavailable; call it instead.\n' +
  'Act on the latest messages; earlier ones are history. When the task is done, call SubagentHandback with your full report.\n' +
  'Call SubagentHandback alone, in a step after you have read the results it reports; never in the same step as another tool.\n' +
  'Reply with exactly one JSON object and nothing else:\n' +
  '{"say": "<short text, may be empty>", "tools": [{"name": "<tool from the catalog>", "input": {...}}]}\n' +
  'Use "tools": [] only when you have nothing to call.\n'

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

// The dir is git-ignored; agents-inc creates it. A fresh thread after a failed resume gets the suffix -2, -3...
const threadPath = (agentId: string, n: number) =>
  `${sessionCwd || '.'}/.scratch/luna-brain/${agentId.replace(/[^\w.-]/g, '_')}${n > 1 ? `-${n}` : ''}.thread`

const cap = (s: string, n: number) => (s.length > n ? `${s.slice(0, n)}\n[truncated ${s.length - n} chars]` : s)

// The `Name: {...}` block of one tool in the BuiltinToolInputs interface; '' when the tool has none.
export function argBlock(types: string, name: string): string {
  const lines = types.split('\n')
  const start = lines.findIndex(l => l.startsWith(`    ${name}: {`))
  if (start < 0) return ''
  if (lines[start].trimEnd().endsWith('{}')) return lines[start].trim()
  const end = lines.findIndex((l, i) => i > start && l === '    }')
  return end < 0 ? '' : lines.slice(start, end + 1).map(l => l.slice(4)).join('\n')
}

export function catalog(tools: readonly Tool[], types: string): string {
  const entries = tools.map(t => {
    const block = argBlock(types, t.name)
    const description = t.mcp ? cap(t.description.split(/(?<=[.!?])\s/)[0], MCP_DESC_CAP) : cap(t.description, DESC_CAP)
    return `- ${t.name}: ${description}${block ? `\n  Arguments:\n${block.replace(/^/gm, '  ')}` : ''}`
  })
  entries.push(`- ${HANDBACK}: Deliver your final report and end your run.\n  Arguments: ${HANDBACK_ARGS}`)
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
  for (const m of messages) {
    for (const b of m.content ?? []) {
      if (b.type === 'text') out.push(`${m.role}: ${String(b.text ?? '')}`)
      else if (b.type === 'tool_use') out.push(`assistant tool call: ${String(b.name)} ${JSON.stringify(b.input ?? {})}`)
      else if (b.type === 'tool_result') out.push(`tool result${b.is_error ? ' (error)' : ''}: ${cap(resultText(b.content), RESULT_CAP)}`)
      else out.push(`${m.role}: [${b.type}]`)
    }
  }
  return out.join('\n')
}

export function buildPrompt(system: string, tools: string, messages: readonly Msg[]): string {
  return `${HEADER}\nSystem prompt:\n${system}\n\nTools:\n${tools}\n\nConversation:\n${render(messages) || '(empty)'}\n`
}

// First balanced {...} in the text, parsed; a reason string when none parses or the shape is wrong.
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

// Plain final text is ignored by the harness; the report has to travel through SubagentHandback.
export function handback(out: Reply): Reply {
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
        argv: ['agents-inc', 'run', '--model', 'luna', '--effort', 'low', '--no-tools', '--cwd', sessionCwd, '--thread', thread],
        cwd: sessionCwd || undefined,
        input: prompt,
      })
      let stdout = ''
      let stderr = ''
      let pending = ''
      const lines: string[] = []
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
          const u = acc.usage ?? { input_tokens: 0, cached_input_tokens: 0, output_tokens: 0 }
          acc.usage = {
            input_tokens: u.input_tokens + (Number(data.input_tokens) || 0),
            cached_input_tokens: u.cached_input_tokens + (Number(data.cached_input_tokens) || 0),
            output_tokens: u.output_tokens + (Number(data.output_tokens) || 0),
          }
        } else if (m[1] === 'event' && typeof data.text === 'string') lines.push(data.text)
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
            if (n.value.code === 0) return { reply: parseReply(stdout, allowed), failed: false }
            const why = `agents-inc run exited ${n.value.code ?? n.value.signal}: ${stderr.slice(-400)}`
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
    const names = [...tools.map(t => t.name), HANDBACK]
    const allowed = new Set(names)
    const composed = await $.prompt.compose({ tools: names }).catch(() => ({ sections: [] }))
    const system = [...composed.sections.map(s => stripModelLines(s.text)), AGENT_PROMPT].join('\n\n')
    const types = await readToolTypes($)
    const api = await $.session.messages({ agentId: id, as: 'api' }).catch(() => [])
    const messages = Array.isArray(api) ? (api as Msg[]) : []
    const full = () => buildPrompt(system, catalog(tools, types), messages)

    const st = agents.get(id) ?? { n: 1, used: false, sent: 0 }
    agents.set(id, st)
    let resumed = st.used
    let prompt = resumed ? `${DELTA_HEADER}${render(messages.slice(st.sent)) || '(nothing new)'}\n` : full()
    let chars = prompt.length
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
    if (!run.failed) st.used = true
    const reply = run.reply
    if (typeof reply !== 'string' && reply !== null) st.sent = messages.length
    const ms = (await $.clock.now()) - t0
    $.ui.log(`luna-brain: step ${e.index} of ${id} took ${ms} ms, prompt ${chars} chars, ${resumed ? 'resumed' : 'fresh'} thread, tools ${names.join(',')}`, { to: 'debug' })
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

    const out: Reply = typeof reply === 'string' ? { say: 'luna reply unparsable', tools: [] } : handback(reply)
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
