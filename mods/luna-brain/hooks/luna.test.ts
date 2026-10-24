import { expect, mock, test } from 'claude-code/testing'

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

// Stands for the engine beneath the plugin: agent.register, agent.spawn, session messages, tools, prompt and the luna process.
async function setup($: Dollar, on: On, opts: { agentId: string; rows?: unknown[]; replies: string[]; calls?: Call[] }) {
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('agent.register', (_$, e) => ({ value: { agent: `luna-brain:${e.name}` } }))
  on('agent.spawn', () => ({ model: 'haiku', agentId: opts.agentId }))
  on('agent.list', () => ({ value: [] }))
  on('session.messages', () => ({ value: opts.rows ?? [text('user', TASK)] }))
  on('tool.list', () => ({ value: TOOLS }))
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'You are Claude Code.', scope: 'shared' }] }))
  on('fs.read', () => ({ value: TYPES }))
  on('process.run', (_$, e) => {
    opts.calls?.push({ argv: e.argv, stdin: e.init?.stdin })
    const stdout = opts.replies.shift() ?? ''
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
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

async function step($: Dollar, agentId: string | undefined) {
  const stream = $.turn.step({ turnId: 't1', index: 0, model: 'haiku', messageCount: 1, agentId })
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
  expect(chunks.map(c => c.kind)).toEqual(['text', 'tool', 'input', 'stop'])
  expect(chunks[1]).toMatchObject({ kind: 'tool', index: 1, name: 'Read' })
  expect(JSON.parse(String(chunks[2].json))).toEqual({ file_path: '/work/a.py' })
  expect(result.stopReason).toBe('tool_use')
  expect(result.toolUses).toEqual([{ name: 'Read', input: { file_path: '/work/a.py' } }])
  expect(result.usage).toBeNull()
  expect(calls[0].argv).toEqual(['agents-inc', 'run', '--model', 'luna', '--effort', 'low', '--no-tools', '--cwd', '/work'])
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
  expect(chunks.map(c => c.kind)).toEqual(['tool', 'input', 'stop'])
  expect(chunks[0]).toMatchObject({ kind: 'tool', name: 'SubagentHandback' })
  expect(JSON.parse(String(chunks[1].json))).toEqual({ message: '42 lines' })
  expect(result).toMatchObject({ answer: '', stopReason: 'tool_use', toolUses: [{ name: 'SubagentHandback', input: { message: '42 lines' } }] })
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

test('an unparsable reply twice yields luna reply unparsable', async ($, on) => {
  const calls: Call[] = []
  await setup($, on, { agentId: 'a4', replies: ['not json', 'still not json'], calls })
  const { chunks, result } = await step($, 'a4')
  expect(calls.length).toBe(2)
  expect(calls[1].stdin).toContain('Your previous reply was rejected')
  expect(chunks).toMatchObject([{ kind: 'text', text: 'luna reply unparsable' }, { kind: 'stop', stopReason: 'end_turn' }])
  expect(result.stopReason).toBe('end_turn')
})
