import { expect, mock, test } from 'claude-code/testing'
import { failureText, pickReply, render, skipsTools, taskText, trimSkillList } from './luna'

type On = Parameters<Parameters<typeof test>[1]>[1]
type Dollar = Parameters<Parameters<typeof test>[1]>[0]
type Call = { argv: readonly string[]; stdin?: string }

const TASK = 'How many lines does /work/a.py have?'
const TYPES = [
  'declare module "claude-code" {',
  '  interface BuiltinToolInputs {',
  '    Bash: {',
  '      /** The command to execute */',
  '      command: string',
  '    }',
  '    Read: {',
  '      /** Absolute path */',
  '      file_path: string',
  '    }',
  '  }',
  '}',
].join('\n')
const TOOLS = [
  { name: 'Read', description: 'Reads a file.', mcp: false },
  { name: 'Bash', description: 'Runs a shell command.', mcp: false },
  { name: 'mcp__x__y', description: 'An MCP tool.', mcp: true },
]
const text = (role: 'user' | 'assistant', t: string) => ({ role, content: [{ type: 'text', text: t }] })
const CUE = '<system-reminder>SubagentHandback: when your work is complete, call SubagentHandback({message: <your full report>})</system-reminder>'

// Stands for the engine beneath the plugin: agent.register, agent.spawn, session messages, tools, prompt and the luna process.
type Run = { out: string; err?: string[]; code?: number }

async function setup($: Dollar, on: On, opts: { agentId: string; rows?: unknown[]; replies: (string | Run)[]; calls?: Call[]; sections?: string[]; task?: string }) {
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('agent.register', (_$, e) => ({ value: { agent: `luna-brain:${e.name}` } }))
  on('agent.spawn', () => ({ model: 'haiku', agentId: opts.agentId }))
  on('agent.list', () => ({ value: [] }))
  on('session.messages', () => ({ value: opts.rows ?? [text('user', `${opts.task ?? TASK}\n${CUE}`)] }))
  on('tool.list', () => ({ value: TOOLS }))
  on('prompt.compose', () => ({ sections: (opts.sections ?? ['You are Claude Code.']).map((t, i) => ({ id: `s${i}`, text: t, scope: 'shared' })) }))
  on('fs.read', () => ({ value: TYPES }))
  on('process.spawn', async function* (_$, e) {
    opts.calls?.push({ argv: e.argv, stdin: e.input })
    const next = opts.replies.shift() ?? ''
    const r = typeof next === 'string' ? { out: next } : next
    // Progress lines first, split mid-line the way a pipe may deliver them.
    for (const line of r.err ?? []) {
      yield { stream: 'stderr' as const, text: line.slice(0, 7) }
      yield { stream: 'stderr' as const, text: `${line.slice(7)}\n` }
    }
    if (r.out) yield { stream: 'stdout' as const, text: r.out }
    return { value: { code: r.code ?? 0, signal: null } }
  })
  on('turn.step', async function* (_$, e) {
    yield { kind: 'text', index: 0, text: 'from anthropic' }
    return { turnId: e.turnId, index: e.index, answer: 'from anthropic', toolUses: [], stopReason: 'end_turn', usage: null }
  })
  on('ui.log', () => ({ value: undefined }))
  mock.clock(on)
  await $.session.start({ cwd: '/work', surface: 'desktop', isInteractive: true })
  await $.agent.spawn({ prompt: TASK, subagentType: 'luna-brain:luna' })
}

async function step($: Dollar, agentId: string | undefined, index = 0) {
  const stream = $.turn.step({ turnId: 't1', index, model: 'haiku', messageCount: 1, agentId })
  const chunks: { kind: string; [k: string]: unknown }[] = []
  for (;;) {
    const n = await stream.next()
    if (n.done) return { chunks, result: n.value }
    chunks.push(n.value)
  }
}

test('a Read call becomes tool chunks and stopReason tool_use', async ($, on) => {
  const calls: Call[] = []
  const reply = JSON.stringify({ say: 'reading', tools: [{ name: 'Read', input: { file_path: '/work/a.py' } }] })
  await setup($, on, { agentId: 'a1', replies: [reply], calls })
  const { chunks, result } = await step($, 'a1')
  expect(chunks.map(c => c.kind)).toEqual(['thinking', 'text', 'tool', 'input', 'stop'])
  expect(chunks[2]).toMatchObject({ kind: 'tool', index: 2, name: 'Read' })
  expect(JSON.parse(String(chunks[3].json))).toEqual({ file_path: '/work/a.py' })
  expect(result.stopReason).toBe('tool_use')
  expect(result.toolUses).toEqual([{ name: 'Read', input: { file_path: '/work/a.py' } }])
  expect(result.usage).toBeNull()
  expect(calls[0].argv).toEqual(['agents-inc', 'run', '--model', 'luna', '--effort', 'low', '--no-tools', '--host-tools', '--cwd', '/work', '--thread', '/work/.scratch/luna-brain/a1.thread'])
  const stdin = calls[0].stdin ?? ''
  expect(stdin).toContain('You are Claude Code.')
  expect(stdin).toContain('- Read: Reads a file.')
  expect(stdin).toContain('file_path: string')
  expect(stdin).toContain('- SubagentHandback:')
  expect(stdin).toContain(`user: ${TASK}`)
  console.log(`fixture prompt size: ${stdin.length} chars`)
})

test('a tool from tool.list that is not a file tool is accepted', async ($, on) => {
  const calls: Call[] = []
  const reply = JSON.stringify({ say: '', tools: [{ name: 'Bash', input: { command: 'wc -l /work/a.py' } }] })
  await setup($, on, { agentId: 'b1', replies: [reply], calls })
  const { result } = await step($, 'b1')
  expect(calls.length).toBe(1)
  expect(result.toolUses).toEqual([{ name: 'Bash', input: { command: 'wc -l /work/a.py' } }])
  expect(result.stopReason).toBe('tool_use')
})

test('an unknown tool name retries once with a correction', async ($, on) => {
  const calls: Call[] = []
  const bad = JSON.stringify({ say: '', tools: [{ name: 'Teleport', input: {} }] })
  const good = JSON.stringify({ say: '', tools: [{ name: 'Read', input: { file_path: '/work/a.py' } }] })
  await setup($, on, { agentId: 'c1', replies: [bad, good], calls })
  const { result } = await step($, 'c1')
  expect(calls.length).toBe(2)
  expect(calls[1].stdin).toContain('Your previous reply was rejected: unknown tool "Teleport"')
  expect(result.toolUses).toEqual([{ name: 'Read', input: { file_path: '/work/a.py' } }])
})

test('tools [] with say becomes a SubagentHandback call', async ($, on) => {
  await setup($, on, { agentId: 'd1', replies: [JSON.stringify({ say: '42 lines', tools: [] })] })
  const { chunks, result } = await step($, 'd1')
  expect(chunks.map(c => c.kind)).toEqual(['thinking', 'text', 'tool', 'input', 'stop'])
  expect(chunks[1]).toMatchObject({ kind: 'text', text: '42 lines' })
  expect(chunks[2]).toMatchObject({ kind: 'tool', name: 'SubagentHandback' })
  expect(JSON.parse(String(chunks[3].json))).toEqual({ message: '42 lines' })
  expect(result).toMatchObject({ answer: '42 lines', stopReason: 'tool_use', toolUses: [{ name: 'SubagentHandback', input: { message: '42 lines' } }] })
})

test('without the hand-back cue a final say ends the turn and SubagentHandback is not offered', async ($, on) => {
  const calls: Call[] = []
  const bad = JSON.stringify({ say: '', tools: [{ name: 'SubagentHandback', input: { message: '42 lines' } }] })
  await setup($, on, { agentId: 'h1', rows: [text('user', TASK)], replies: [bad, JSON.stringify({ say: '42 lines', tools: [] })], calls })
  const { chunks, result } = await step($, 'h1')
  expect(calls[0].stdin).not.toContain('- SubagentHandback:')
  expect(calls[0].stdin).toContain('There is no SubagentHandback tool here')
  expect(calls[1].stdin).toContain('unknown tool "SubagentHandback"')
  expect(chunks.map(c => c.kind)).toEqual(['thinking', 'text', 'stop'])
  expect(result).toMatchObject({ answer: '42 lines', stopReason: 'end_turn', toolUses: [] })
})

test('a SubagentHandback next to another call is dropped until the results exist', async ($, on) => {
  const reply = JSON.stringify({ say: '', tools: [{ name: 'Bash', input: { command: 'wc -l /work/a.py' } }, { name: 'SubagentHandback', input: { message: 'pending' } }] })
  await setup($, on, { agentId: 'g1', replies: [reply] })
  const { result } = await step($, 'g1')
  expect(result.toolUses).toEqual([{ name: 'Bash', input: { command: 'wc -l /work/a.py' } }])
})

test('tool results are capped and a later user message follows the first', async ($, on) => {
  const rows = [
    text('user', TASK),
    { role: 'assistant', content: [{ type: 'tool_use', id: 'u1', name: 'Read', input: { file_path: '/work/a.py' } }] },
    { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'u1', content: 'x'.repeat(30000) }] },
    text('user', '<system-reminder>Your final report is delivered through SubagentHandback</system-reminder>'),
    text('user', 'Actually count /work/b.py instead.'),
  ]
  const calls: Call[] = []
  await setup($, on, { agentId: 'e1', rows, replies: [JSON.stringify({ say: 'ok', tools: [] })], calls })
  await step($, 'e1')
  const stdin = calls[0].stdin ?? ''
  expect(stdin).toContain('assistant tool call: Read {"file_path":"/work/a.py"}')
  expect(stdin).toContain('[truncated 10000 chars]')
  expect(stdin.indexOf(TASK)).toBeLessThan(stdin.indexOf('Actually count /work/b.py instead.'))
  expect(stdin).toContain('<system-reminder>Your final report is delivered through SubagentHandback</system-reminder>')
})

test('a non-luna agentId passes through to next', async ($, on) => {
  const calls: Call[] = []
  await setup($, on, { agentId: 'a3', replies: [], calls })
  const { chunks, result } = await step($, 'other')
  expect(chunks).toMatchObject([{ kind: 'text', text: 'from anthropic' }])
  expect(result.answer).toBe('from anthropic')
  expect(calls.length).toBe(0)
})

test('the second step sends only the new messages on the same thread', async ($, on) => {
  const calls: Call[] = []
  const first = JSON.stringify({ say: '', tools: [{ name: 'Read', input: { file_path: '/work/a.py' } }] })
  const opts = { agentId: 'h1', replies: [first, JSON.stringify({ say: 'done', tools: [] })], calls, rows: [text('user', TASK)] as unknown[] }
  await setup($, on, opts)
  await step($, 'h1')
  opts.rows = [
    text('user', TASK),
    { role: 'assistant', content: [{ type: 'tool_use', id: 'u1', name: 'Read', input: { file_path: '/work/a.py' } }] },
    { role: 'user', content: [{ type: 'tool_result', tool_use_id: 'u1', content: '12 lines' }] },
  ]
  await step($, 'h1', 1)
  expect(calls.length).toBe(2)
  const [one, two] = calls
  expect(one.argv.slice(-2)).toEqual(['--thread', '/work/.scratch/luna-brain/h1.thread'])
  expect(two.argv.slice(-2)).toEqual(['--thread', '/work/.scratch/luna-brain/h1.thread'])
  const delta = two.stdin ?? ''
  expect(delta).toContain('New messages since your last reply.')
  expect(delta).toContain('tool result: 12 lines')
  expect(delta).not.toContain('System prompt:')
  expect(delta).not.toContain('- Read: Reads a file.')
  expect(delta).not.toContain(`user: ${TASK}`)
  console.log(`fixture prompt sizes: first ${one.stdin?.length} chars, second ${delta.length} chars`)
})

test('progress lines become thinking chunks before the stop chunk', async ($, on) => {
  const run: Run = {
    out: JSON.stringify({ say: '', tools: [{ name: 'Read', input: { file_path: '/work/a.py' } }] }),
    err: [
      'agents-inc run: record {"model":"luna","slug":"gpt-6-luna","tools":"off"}',
      `agents-inc run: event ${JSON.stringify({ kind: 'reasoning', text: 'look at the file' })}`,
      `agents-inc run: event ${JSON.stringify({ kind: 'agent_message', text: 'calling Read' })}`,
      'agents-inc run: usage {"input_tokens":1000,"cached_input_tokens":800,"output_tokens":50}',
    ],
  }
  await setup($, on, { agentId: 'i1', replies: [run] })
  const { chunks, result } = await step($, 'i1')
  expect(chunks.map(c => c.kind)).toEqual(['thinking', 'thinking', 'thinking', 'tool', 'input', 'stop'])
  expect(chunks[1]).toMatchObject({ index: 0, text: 'look at the file' })
  expect(chunks[2]).toMatchObject({ index: 0, text: 'calling Read' })
  const usage = { input_tokens: 200, output_tokens: 50, cache_read_input_tokens: 800, cache_creation_input_tokens: 0, model: 'gpt-6-luna' }
  expect(chunks[5]).toMatchObject({ kind: 'stop', usage })
  expect(result.usage).toEqual(usage)
})

test('usage falls back to the model name luna when no record line came', async ($, on) => {
  const run: Run = { out: JSON.stringify({ say: 'x', tools: [] }), err: ['agents-inc run: usage {"input_tokens":10,"cached_input_tokens":0,"output_tokens":2}'] }
  await setup($, on, { agentId: 'j1', replies: [run] })
  const { result } = await step($, 'j1')
  expect(result.usage).toEqual({ input_tokens: 10, output_tokens: 2, cache_read_input_tokens: 0, cache_creation_input_tokens: 0, model: 'luna' })
})

test('lines naming the placeholder model are dropped from the system prompt', async ($, on) => {
  const calls: Call[] = []
  const sections = ['You are Claude Code.\nYou are powered by the model named Haiku 5.5. The exact model ID is claude-haiku-5-5.\nKeep it short.']
  await setup($, on, { agentId: 'k1', replies: [JSON.stringify({ say: 'x', tools: [] })], calls, sections })
  await step($, 'k1')
  const stdin = calls[0].stdin ?? ''
  expect(stdin).toContain('You are Claude Code.\nKeep it short.')
  expect(stdin).not.toContain('You are powered by the model')
  expect(stdin).not.toContain('The exact model ID is')
  expect(stdin).toContain('You are luna (OpenAI GPT-6 Luna, model gpt-6-luna, run through Codex).')
})

test('a retry on a resumed thread sends only the correction line', async ($, on) => {
  const calls: Call[] = []
  const bad = JSON.stringify({ say: '', tools: [{ name: 'Teleport', input: {} }] })
  const good = JSON.stringify({ say: 'ok', tools: [] })
  await setup($, on, { agentId: 'l1', replies: [good, bad, good], calls })
  await step($, 'l1')
  await step($, 'l1', 1)
  expect(calls.length).toBe(3)
  expect(calls[2].stdin).toContain('Your previous reply was rejected: unknown tool "Teleport"')
  expect(calls[2].stdin).not.toContain('New messages since')
  expect(calls[2].stdin).not.toContain('System prompt:')
})

test('a failed resume retries fresh with the full prompt and a new thread path', async ($, on) => {
  const calls: Call[] = []
  const good = JSON.stringify({ say: 'ok', tools: [] })
  await setup($, on, { agentId: 'm1', replies: [good, { out: '', code: 1 }, good, good], calls })
  await step($, 'm1')
  const { result } = await step($, 'm1', 1)
  expect(calls.length).toBe(3)
  expect(calls[1].argv.slice(-1)).toEqual(['/work/.scratch/luna-brain/m1.thread'])
  expect(calls[2].argv.slice(-1)).toEqual(['/work/.scratch/luna-brain/m1-2.thread'])
  expect(calls[2].stdin).toContain('System prompt:')
  expect(calls[2].stdin).toContain(`user: ${TASK}`)
  expect(result.answer).toBe('ok')
  await step($, 'm1', 2) // the new thread is used from here on
  expect(calls[3].argv.slice(-1)).toEqual(['/work/.scratch/luna-brain/m1-2.thread'])
  expect(calls[3].stdin).toContain('New messages since')
})

test('an unparsable reply twice yields luna reply unparsable', async ($, on) => {
  const calls: Call[] = []
  await setup($, on, { agentId: 'a4', replies: ['not json', 'still not json'], calls })
  const { chunks, result } = await step($, 'a4')
  expect(calls.length).toBe(2)
  expect(calls[1].stdin).toContain('Your previous reply was rejected')
  expect(chunks).toMatchObject([{ kind: 'thinking' }, { kind: 'text', text: 'luna reply unparsable' }, { kind: 'stop', stopReason: 'end_turn' }])
  expect(result.stopReason).toBe('end_turn')
})

test('the skill listing keeps only skill names, colons in plugin names included', async () => {
  const text = 'hi\n<system-reminder>\nThe following skills are available for use with the Skill tool:\n\n- accelerate\n' +
    '- caveman: Terse voice.\n  more detail\n- code-review:code-review: Code review a pull request\n</system-reminder>\nbye'
  expect(trimSkillList(text)).toBe('hi\n<system-reminder>\nThe following skills are available for use with the Skill tool:\n' +
    'accelerate, caveman, code-review:code-review\n</system-reminder>\nbye')
})

test('a failed run reports its stderr without MCP noise or progress lines', async () => {
  const stderr = 'x ERROR rmcp::transport::worker: worker quit\nagents-inc run: usage {"input_tokens":1}\n' +
    'agents-inc run: returned an empty reply\n'
  expect(failureText(stderr)).toBe('agents-inc run: returned an empty reply')
  expect(failureText('x ERROR rmcp::transport::worker: quit\n')).toBe('(no other stderr)')
})

test('a resumed thread reports only the rise in Codex running totals', async ($, on) => {
  const usage = (i: number, c: number, o: number) => `agents-inc run: usage {"input_tokens":${i},"cached_input_tokens":${c},"output_tokens":${o}}`
  const reply = JSON.stringify({ say: '', tools: [{ name: 'Read', input: { file_path: '/work/a.py' } }] })
  const replies: Run[] = [{ out: reply, err: [usage(1000, 0, 10)] }, { out: reply, err: [usage(2100, 1000, 25)] }]
  await setup($, on, { agentId: 'u1', replies })
  await step($, 'u1', 0)
  const { result } = await step($, 'u1', 1)
  expect(result.usage).toMatchObject({ input_tokens: 100, cache_read_input_tokens: 1000, output_tokens: 15 })
})

test('a conversation that shrank starts a fresh thread with the whole prompt', async ($, on) => {
  const calls: Call[] = []
  const reply = JSON.stringify({ say: '', tools: [{ name: 'Read', input: { file_path: '/work/a.py' } }] })
  const rows = [text('user', TASK), text('assistant', 'a'), text('user', 'b')]
  await setup($, on, { agentId: 'c1', rows, replies: [reply, reply], calls })
  await step($, 'c1', 0)
  rows.splice(1)
  await step($, 'c1', 1)
  expect(calls[1].argv.at(-1)).toMatch(/c1-2\.thread$/)
  expect(calls[1].stdin).toContain('Conversation:')
})

test('a refusal before any tool ran gets one push, and the pushed reply is used', async ($, on) => {
  const calls: Call[] = []
  const no = JSON.stringify({ say: 'I can’t run tools in this environment.', tools: [] })
  const yes = JSON.stringify({ say: '', tools: [{ name: 'Bash', input: { command: 'wc -l /work/a.py' } }] })
  await setup($, on, { agentId: 'r1', replies: [no, yes], calls })
  const { result } = await step($, 'r1')
  expect(calls.length).toBe(2)
  expect(calls[1].stdin).toContain('Every catalog tool is real')
  expect(result.toolUses).toEqual([{ name: 'Bash', input: { command: 'wc -l /work/a.py' } }])
})

test('a value given without running the tool the task names gets one push', async ($, on) => {
  const calls: Call[] = []
  const made = JSON.stringify({ say: 'A=0', tools: [] })
  const yes = JSON.stringify({ say: '', tools: [{ name: 'Bash', input: { command: 'wc -l a.txt' } }] })
  await setup($, on, { agentId: 'f1', replies: [made, yes], calls, task: 'Run wc -l a.txt with Bash; report A=<n>.' })
  const { result } = await step($, 'f1')
  expect(calls.length).toBe(2)
  expect(calls[1].stdin).toContain('never from a snapshot or a guess')
  expect(result.toolUses).toEqual([{ name: 'Bash', input: { command: 'wc -l a.txt' } }])
})

test('skipsTools reads catalog tool names in the task, not in harness reminders', () => {
  const say = (t: string) => ({ say: t, tools: [] })
  expect(skipsTools(say('A=0'), false, 'Run wc -l a.txt with Bash', ['Bash', 'Read'])).toBe(true)
  expect(skipsTools(say('Lorem — ipsum'), false, 'Write one Latin sentence. Use no tools.', ['Bash', 'Read', 'Write'])).toBe(false)
  expect(skipsTools(say('B=95'), false, 'Count lines, then Read b.txt', ['Read'])).toBe(true)
  expect(skipsTools(say('done'), false, 'Use the Grep tool on src', ['Grep'])).toBe(true)
  expect(skipsTools(say('A=0'), false, 'Run wc with Bash', ['SubagentHandback'])).toBe(false)
  const msg = (text: string) => ({ role: 'user' as const, content: [{ type: 'text', text }] })
  expect(taskText([msg('Write a poem.<system-reminder>Bash and Read are available</system-reminder>')])).toBe('Write a poem.')
})

test('a Read result drops the numbered empty line after the final newline', () => {
  const msgs = [
    { role: 'assistant' as const, content: [{ type: 'tool_use', id: 't1', name: 'Read', input: { file_path: 'b.txt' } }] },
    { role: 'user' as const, content: [{ type: 'tool_result', tool_use_id: 't1', content: '1\t1\n2\t2\n3\t' }] },
  ]
  expect(render(msgs)).toBe('assistant tool call: Read {"file_path":"b.txt"}\ntool result: 1\t1\n2\t2')
  const bare = [msgs[0], { role: 'user' as const, content: [{ type: 'tool_result', tool_use_id: 't1', content: '1\t1\n2\t2\n3' }] }]
  expect(render(bare)).toBe(render(msgs))
  const digits = [msgs[0], { role: 'user' as const, content: [{ type: 'tool_result', tool_use_id: 't1', content: '1\t1\n2\t22' }] }]
  expect(render(digits).endsWith('2\t22')).toBe(true)
  const reminded = [msgs[0], { role: 'user' as const, content: [{ type: 'tool_result', tool_use_id: 't1', content: '1\t1\n2\t2\n3\n\n<system-reminder>\nx\n</system-reminder>\n' }] }]
  expect(render(reminded)).toBe('assistant tool call: Read {"file_path":"b.txt"}\ntool result: 1\t1\n2\t2\n\n<system-reminder>\nx\n</system-reminder>\n')
})

test('an empty pushed reply keeps the first answer', async ($, on) => {
  const calls: Call[] = []
  const first = JSON.stringify({ say: 'Lorem ipsum — text', tools: [] })
  await setup($, on, { agentId: 'e1', replies: [first, JSON.stringify({ say: '', tools: [] })], calls, task: 'Answer with Bash output.' })
  const { result } = await step($, 'e1')
  expect(calls.length).toBe(2)
  expect(result.answer).toBe('Lorem ipsum — text')
})

test('skipsTools on a refusal fires before any tool result and only without tool calls', () => {
  const say = (t: string, tools: { name: string; input: unknown }[] = []) => ({ say: t, tools })
  expect(skipsTools(say("I can't run Bash here."), false)).toBe(true)
  expect(skipsTools(say('the host’s execution tool is disabled'), false)).toBe(true)
  expect(skipsTools(say("I can't run Bash here."), true)).toBe(false)
  expect(skipsTools(say("I can't run Bash here.", [{ name: 'Bash', input: {} }]), false)).toBe(false)
  expect(skipsTools(say('A=173'), false)).toBe(false)
  expect(skipsTools('no JSON object in the reply', false)).toBe(false)
})

test('the first message that requests tools wins over a later guessed answer', () => {
  const call = JSON.stringify({ say: '', tools: [{ name: 'Bash', input: { command: 'wc -l b.txt' } }] })
  const guess = JSON.stringify({ say: 'B=1', tools: [] })
  const allowed = new Set(['Bash'])
  expect(pickReply([call, guess], guess, allowed)).toEqual({ say: '', tools: [{ name: 'Bash', input: { command: 'wc -l b.txt' } }] })
  expect(pickReply([guess], guess, allowed)).toEqual({ say: 'B=1', tools: [] })
  const unknown = JSON.stringify({ say: '', tools: [{ name: 'Nope', input: {} }] })
  expect(pickReply([unknown, guess], guess, allowed)).toEqual({ say: 'B=1', tools: [] })
})

test('a step takes the tool request from the progress events when the last message guesses', async ($, on) => {
  const call = JSON.stringify({ say: '', tools: [{ name: 'Bash', input: { command: 'wc -l a.txt' } }] })
  const guess = JSON.stringify({ say: 'A=1', tools: [] })
  const ev = (text: string) => `agents-inc run: event ${JSON.stringify({ kind: 'agent_message', text })}`
  const calls: Call[] = []
  await setup($, on, { agentId: 'p1', replies: [{ out: guess, err: [ev(call), ev(guess)] }], calls })
  const { result } = await step($, 'p1')
  expect(calls.length).toBe(1)
  expect(result.toolUses).toEqual([{ name: 'Bash', input: { command: 'wc -l a.txt' } }])
})
