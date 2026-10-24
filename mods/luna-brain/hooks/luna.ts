import type { Register } from 'claude-code'

const AGENT = 'luna'
const AGENT_TYPES = ['luna-brain:luna', 'luna']
const TOOLS = ['Read', 'Grep', 'Glob']
const RESULT_CAP = 20_000
const RUN_TIMEOUT_MS = 300_000

const HEADER =
  'You are the reasoning step of an agent loop. You cannot run tools yourself. The host runs tools for you.\n' +
  'Tools: Read {"file_path": abs path}; Grep {"pattern": str, "path": str}; Glob {"pattern": str}.\n' +
  'Reply with exactly one JSON object and nothing else:\n' +
  '{"say": "<short text for the user, may be empty>", "tools": [{"name": "<tool>", "input": {...}}]}\n' +
  'Use "tools": [] when you are done; then "say" holds your final answer.\n'

const AGENT_PROMPT =
  'You are a read-only research agent. Use Read, Grep and Glob to answer the task, then give a short final answer.'

type Reply = { say: string; tools: { name: string; input: unknown }[] }
type Row = {
  role: 'user' | 'assistant'
  text: string
  toolUses: { tool_use_id: string; tool: string; input: unknown; text?: string }[]
  toolResults?: { tool_use_id: string; text: string }[]
}

const lunaIds = new Set<string>()
let sessionCwd = ''

const cap = (s: string) => (s.length > RESULT_CAP ? `${s.slice(0, RESULT_CAP)}\n[truncated ${s.length - RESULT_CAP} chars]` : s)

// Plain text of the rows after the task: user text, assistant text, each call as name + JSON, each result capped.
export function serialize(rows: readonly Row[]): string {
  const answered = new Set<string>()
  for (const r of rows) for (const t of r.toolResults ?? []) answered.add(t.tool_use_id)
  const out: string[] = []
  for (const r of rows) {
    if (r.text) out.push(`${r.role}: ${r.text}`)
    for (const u of r.toolUses ?? []) {
      out.push(`assistant tool call: ${u.tool} ${JSON.stringify(u.input)}`)
      if (u.text !== undefined && !answered.has(u.tool_use_id)) out.push(`tool result: ${cap(u.text)}`)
    }
    for (const t of r.toolResults ?? []) out.push(`tool result: ${cap(t.text)}`)
  }
  return out.join('\n')
}

export function buildPrompt(rows: readonly Row[]): string {
  const first = rows[0]
  const task = first && first.role === 'user' ? first.text : ''
  const rest = first && first.role === 'user' ? rows.slice(1) : rows
  const transcript = serialize(rest) || '(empty, this is step 0)'
  return `${HEADER}\nTask: ${task}\n\nTranscript so far: ${transcript}\n`
}

// First balanced {...} in the text, parsed; a reason string when none parses or the shape is wrong.
export function parseReply(stdout: string): Reply | string {
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
        return shape(obj)
      }
    }
  }
  return 'no JSON object in the reply'
}

function shape(obj: unknown): Reply | string {
  if (typeof obj !== 'object' || obj === null) return 'reply is not an object'
  const o = obj as { say?: unknown; tools?: unknown }
  const tools = o.tools === undefined ? [] : o.tools
  if (!Array.isArray(tools)) return '"tools" is not a list'
  const list: Reply['tools'] = []
  for (const t of tools) {
    const name = (t as { name?: unknown } | null)?.name
    if (typeof name !== 'string' || !TOOLS.includes(name)) return `unknown tool ${JSON.stringify(name)}; use only ${TOOLS.join(', ')}`
    list.push({ name, input: (t as { input?: unknown }).input ?? {} })
  }
  return { say: typeof o.say === 'string' ? o.say : '', tools: list }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    sessionCwd = e.cwd
    await $.agent.register({
      name: AGENT,
      description: 'Read-only research agent whose reasoning is done by luna (Codex). Spike; use only when asked for luna.',
      prompt: AGENT_PROMPT,
      tools: TOOLS,
      model: 'haiku', // placeholder: turn.step never calls it for this agent
      maxTurns: 10,
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
    const aborted = new Promise<null>(res => {
      if (next.signal.aborted) res(null)
      else next.signal.addEventListener('abort', () => res(null), { once: true })
    })

    const ask = async (prompt: string): Promise<Reply | string | null> => {
      const run = $.process
        .run(['agents-inc', 'run', '--model', 'luna', '--effort', 'low', '--no-tools', '--cwd', sessionCwd], {
          cwd: sessionCwd || undefined,
          stdin: prompt,
          timeoutMs: RUN_TIMEOUT_MS,
        })
        .then(r => (r.exitCode === 0 ? parseReply(r.stdout) : `agents-inc run exited ${r.exitCode}`))
        .catch(err => `agents-inc run failed: ${String((err as Error)?.message ?? err)}`)
      return Promise.race([run, aborted])
    }

    const rows = await $.session.messages({ agentId: id })
    const prompt = Array.isArray(rows) ? buildPrompt(rows as Row[]) : buildPrompt([])

    let reply = await ask(prompt)
    if (typeof reply === 'string') {
      reply = await ask(`${prompt}\nYour previous reply was rejected: ${reply}. Reply with exactly one JSON object, only the listed tools.\n`)
    }
    const ms = (await $.clock.now()) - t0
    $.ui.log(`luna-brain: step ${e.index} of ${id} took ${ms} ms`, { to: 'debug' })

    if (reply === null) return { turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: null, usage: null }

    const out: Reply = typeof reply === 'string' ? { say: 'luna reply unparsable', tools: [] } : reply
    let index = 0
    if (out.say) yield { kind: 'text', index: index++, text: out.say }
    for (const [n, tool] of out.tools.entries()) {
      yield { kind: 'tool', index, id: `luna_${e.turnId}_${e.index}_${n}`, name: tool.name }
      yield { kind: 'input', index, json: JSON.stringify(tool.input) }
      index++
    }
    const stopReason = out.tools.length > 0 ? 'tool_use' : 'end_turn'
    yield { kind: 'stop', stopReason, usage: null }
    return { turnId: e.turnId, index: e.index, answer: out.say, toolUses: out.tools, stopReason, usage: null }
  })
}
