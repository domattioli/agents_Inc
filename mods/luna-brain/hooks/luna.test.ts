import { expect, mock, test } from 'claude-code/testing'

type On = Parameters<Parameters<typeof test>[1]>[1]
type Dollar = Parameters<Parameters<typeof test>[1]>[0]

const TASK = 'How many lines does /work/a.py have?'

// Stands for the engine beneath the plugin: agent.register, agent.spawn, session rows and the luna process.
async function setup($: Dollar, on: On, opts: { agentId: string; rows?: unknown[]; replies: string[]; calls?: { argv: readonly string[]; stdin?: string }[] }) {
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('agent.register', (_$, e) => ({ value: { agent: `luna-brain:${e.name}` } }))
  on('agent.spawn', () => ({ model: 'haiku', agentId: opts.agentId }))
  on('agent.list', () => ({ value: [] }))
  on('session.messages', () => ({ value: opts.rows ?? [{ role: 'user', text: TASK, toolUses: [] }] }))
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
  const calls: { argv: readonly string[]; stdin?: string }[] = []
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
  expect(calls[0].stdin).toContain(`Task: ${TASK}`)
  expect(calls[0].stdin).toContain('Transcript so far: (empty, this is step 0)')
})

test('a final step yields the text and end_turn', async ($, on) => {
  const rows = [
    { role: 'user', text: TASK, toolUses: [] },
    { role: 'assistant', text: '', toolUses: [{ tool_use_id: 'u1', tool: 'Read', input: { file_path: '/work/a.py' } }] },
    { role: 'user', text: '', toolUses: [], toolResults: [{ tool_use_id: 'u1', text: 'x'.repeat(30000), isError: false }] },
  ]
  const calls: { argv: readonly string[]; stdin?: string }[] = []
  await setup($, on, { agentId: 'a2', rows, replies: [JSON.stringify({ say: '42 lines', tools: [] })], calls })
  const { chunks, result } = await step($, 'a2')
  expect(chunks).toMatchObject([{ kind: 'text', text: '42 lines' }, { kind: 'stop', stopReason: 'end_turn' }])
  expect(result).toMatchObject({ answer: '42 lines', toolUses: [], stopReason: 'end_turn' })
  const stdin = calls[0].stdin ?? ''
  expect(stdin).toContain('assistant tool call: Read {"file_path":"/work/a.py"}')
  expect(stdin).toContain('[truncated 10000 chars]')
})

test('a non-luna agentId passes through to next', async ($, on) => {
  const calls: { argv: readonly string[]; stdin?: string }[] = []
  await setup($, on, { agentId: 'a3', replies: [], calls })
  const { chunks, result } = await step($, 'other')
  expect(chunks).toMatchObject([{ kind: 'text', text: 'from anthropic' }])
  expect(result.answer).toBe('from anthropic')
  expect(calls.length).toBe(0)
})

test('an unparsable reply twice yields luna reply unparsable', async ($, on) => {
  const calls: { argv: readonly string[]; stdin?: string }[] = []
  await setup($, on, { agentId: 'a4', replies: ['not json', 'still not json'], calls })
  const { chunks, result } = await step($, 'a4')
  expect(calls.length).toBe(2)
  expect(calls[1].stdin).toContain('Your previous reply was rejected')
  expect(chunks).toMatchObject([{ kind: 'text', text: 'luna reply unparsable' }, { kind: 'stop', stopReason: 'end_turn' }])
  expect(result.stopReason).toBe('end_turn')
})
