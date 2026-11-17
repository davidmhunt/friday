export const meta = {
  name: 'execute',
  description: 'Execute one approved friday directive: implement each step, gate on its Verify command, independent review, push the branch and open a PR',
  whenToUse: 'After the user approves a directive in docs/directives/. Pass the directive id, e.g. /friday:execute core-03',
  phases: [
    { title: 'Prepare', detail: 'read the directive, switch to its branch, mark it active' },
    { title: 'Implement', detail: 'one implementer per step, in order' },
    { title: 'Verify', detail: 'run Verify; fix and rerun until it passes or stops making progress' },
    { title: 'Review', detail: 'independent Opus verifier against the directive' },
    { title: 'Land', detail: 'log, push the branch, open the PR' },
  ],
}

// ---------------------------------------------------------------- input
const id = String((args && typeof args === 'object' ? args.id : args) || '').trim()
if (!/^[a-z0-9][a-z0-9_-]*-\d{2,}$/.test(id)) {
  throw new Error('usage: /friday:execute <directive id>, e.g. /friday:execute core-03')
}
const MAX_FIX_ROUNDS = 4        // verify -> fix cycles before giving up
const MAX_SAME_FAILURE = 2      // the same failure this many rounds in a row = no progress

// ---------------------------------------------------------------- schemas
const PREP = {
  type: 'object',
  required: ['ready', 'reason', 'base', 'title', 'verify', 'hardware', 'steps'],
  properties: {
    ready: { type: 'boolean' },
    reason: { type: 'string', description: 'why not ready, or empty' },
    base: { type: 'string', description: 'the branch HEAD was on before switching to friday/<id>' },
    title: { type: 'string' },
    verify: { type: 'string', description: 'the Verify: command, verbatim' },
    hardware: { type: 'string' },
    steps: {
      type: 'array',
      items: {
        type: 'object',
        required: ['n', 'text', 'heavy'],
        properties: { n: { type: 'integer' }, text: { type: 'string' }, heavy: { type: 'boolean' } },
      },
    },
  },
}
const STEP = {
  type: 'object',
  required: ['status', 'summary', 'commit', 'question'],
  properties: {
    status: { type: 'string', enum: ['done', 'needs_user', 'failed'] },
    summary: { type: 'string', description: 'files changed and the check run, with its last lines' },
    commit: { type: 'string', description: 'commit hash, or empty' },
    question: { type: 'string', description: 'the decision the user must make, with your recommendation; empty if none' },
  },
}
const VERIFY = {
  type: 'object',
  required: ['passed', 'exit_code', 'signature', 'tail'],
  properties: {
    passed: { type: 'boolean' },
    exit_code: { type: 'integer' },
    signature: { type: 'string', description: 'the first failing test or error line, verbatim; empty if passed' },
    tail: { type: 'string', description: 'last 60 lines of output' },
  },
}
const REVIEW = {
  type: 'object',
  required: ['gaps', 'confidence'],
  properties: {
    gaps: {
      type: 'array',
      items: {
        type: 'object',
        required: ['where', 'problem', 'evidence'],
        properties: { where: { type: 'string' }, problem: { type: 'string' }, evidence: { type: 'string' } },
      },
    },
    confidence: { type: 'string', description: 'why you are confident in the verdict' },
  },
}
const LAND = {
  type: 'object',
  required: ['exit_code', 'output'],
  properties: {
    exit_code: { type: 'integer', description: 'exit code of friday land' },
    output: { type: 'string', description: 'its output, verbatim' },
  },
}

// ---------------------------------------------------------------- helpers
const directive = `docs/directives/${id}.md`

async function block(reason) {
  log(`${id} blocked: ${reason}`)
  await agent(
    `Directive ${id} has to stop for the user. In the repo root: append a dated entry to the "## Log" section of ${directive} that says: "Blocked: ${reason.replace(/`/g, "'")}"; then run \`friday finish ${id} --blocked "<one-line summary>"\`; then commit ${directive} with a message whose last line is \`Directive: ${id}\`. Do not push.`,
    { agentType: 'friday:implementer', schema: STEP, label: 'record block', phase: 'Land' },
  )
  return `${id} is blocked and needs you: ${reason}`
}

async function verifyLoop(d, label) {
  let last = '', same = 0
  for (let round = 1; ; round++) {
    const v = await agent(
      `Run the Verify command of friday directive ${id} from the repo root, exactly as written, and wait for it to finish (it can take several minutes):\n\n${d.verify}\n\nReturn whether it passed, its exit code, the first failing test or error line verbatim, and the last 60 lines of output.`,
      { agentType: 'friday:runner', schema: VERIFY, label: `${label} verify ${round}`, phase: 'Verify' },
    )
    if (v && v.passed) return { ok: true, rounds: round }
    const sig = v ? v.signature : 'the verify run returned nothing'
    same = sig === last ? same + 1 : 1
    last = sig
    if (round >= MAX_FIX_ROUNDS || same >= MAX_SAME_FAILURE) {
      return { ok: false, why: `Verify still fails after ${round} round(s): ${sig}` }
    }
    const fix = await agent(
      `Directive ${id} (${directive}): its Verify command fails.\n\nCommand: ${d.verify}\nFirst failure: ${sig}\nOutput tail:\n${v ? v.tail : '(none)'}\n\nFind and fix the root cause within the directive's scope. Do not weaken, skip or delete tests or checks. Run the failing part again to confirm, then commit (last line \`Directive: ${id}\`).`,
      { agentType: 'friday:implementer', schema: STEP, label: `${label} fix ${round}`, phase: 'Verify' },
    )
    if (fix && fix.status === 'needs_user') return { ok: false, why: fix.question }
  }
}

// ---------------------------------------------------------------- prepare
phase('Prepare')
const d = await agent(
  `Prepare friday directive ${id} for execution. From the repo root:\n1. Read ${directive}. If its Status is not "approved" or "running@...", return ready=false with the reason and change nothing.\n2. Record the current branch as base. Switch to friday/${id}: \`git switch friday/${id}\` if it exists, else \`git switch -c friday/${id}\`.\n3. Run \`friday start ${id} --no-gate\` and commit ${directive} (message last line \`Directive: ${id}\`).\nReturn the directive's title, Verify command verbatim, Hardware line, and its numbered Steps (heavy = the step is tagged [heavy]).`,
  { agentType: 'friday:implementer', schema: PREP, label: `prepare ${id}` },
)
if (!d || !d.ready) return `${id} not started: ${d ? d.reason : 'could not read the directive'}`
log(`${id}: ${d.title} (${d.steps.length} steps)`)

// ---------------------------------------------------------------- implement
phase('Implement')
for (const s of d.steps) {
  const opts = { agentType: 'friday:implementer', schema: STEP, label: `step ${s.n}${s.heavy ? ' [heavy]' : ''}`, phase: 'Implement' }
  if (s.heavy) opts.model = 'opus'
  const r = await agent(
    `Implement step ${s.n} of friday directive ${id} (${directive}) on branch friday/${id}.\n\nStep ${s.n}: ${s.text}\n\nRead the whole directive first (goal, out of scope). Earlier steps are already committed. Prove the step with a focused check, then commit (last line \`Directive: ${id}\`).`,
    opts,
  )
  if (!r) return await block(`step ${s.n} agent did not return`)
  if (r.status === 'needs_user') return await block(`step ${s.n}: ${r.question}`)
  if (r.status === 'failed') return await block(`step ${s.n} failed: ${r.summary}`)
}

// ---------------------------------------------------------------- verify + review
phase('Verify')
let v = await verifyLoop(d, 'initial')
if (!v.ok) return await block(v.why)

phase('Review')
let review = await agent(
  `Review friday directive ${id}: read ${directive}, then the change: \`git diff ${d.base}...HEAD\` and \`git log --oneline ${d.base}..HEAD\`. Its Verify command already passes. Report only gaps that affect correctness or the directive's stated requirements.`,
  { agentType: 'friday:verifier', schema: REVIEW, label: 'verifier', phase: 'Review' },
)
if (review && review.gaps.length) {
  const list = review.gaps.map((g, i) => `${i + 1}. ${g.where}: ${g.problem} (evidence: ${g.evidence})`).join('\n')
  const fix = await agent(
    `An independent review of directive ${id} (${directive}) found these gaps:\n${list}\n\nFix each one that is real, within scope. If you disagree with one, leave it and explain why with evidence. Commit (last line \`Directive: ${id}\`).`,
    { agentType: 'friday:implementer', schema: STEP, label: 'fix review gaps', phase: 'Review' },
  )
  if (fix && fix.status === 'needs_user') return await block(fix.question)
  v = await verifyLoop(d, 'after review')
  if (!v.ok) return await block(v.why)
  review = await agent(
    `Second review of friday directive ${id}. Earlier gaps:\n${list}\n\nRead ${directive} and \`git diff ${d.base}...HEAD\`. Report only gaps that still affect correctness or the stated requirements.`,
    { agentType: 'friday:verifier', schema: REVIEW, label: 'verifier (2nd)', phase: 'Review' },
  )
  if (review && review.gaps.length) {
    return await block(`review gaps remain: ${review.gaps.map(g => `${g.where}: ${g.problem}`).join('; ')}`)
  }
}

// ---------------------------------------------------------------- land
phase('Land')
const land = await agent(
  `Land friday directive ${id} from the repo root, on branch friday/${id}:\n1. Append a dated entry to the "## Log" section of ${directive}: the commits (\`git log --oneline ${d.base}..HEAD\`), "Verify passed: ${d.verify.replace(/`/g, "'")}", and "Independent review: no gaps".\n2. Run \`friday finish ${id}\`, then commit ${directive} (last line \`Directive: ${id}\`).\n3. Run exactly \`friday land ${id} --base ${d.base}\` (it pushes the branch and opens the PR; do not push or call gh yourself). If it needs a permission, ask for it; do not work around it.\nReturn its exit code and its output verbatim.`,
  { agentType: 'friday:implementer', schema: LAND, label: 'land' },
)
const LAND_MEANING = {
  0: 'PR open',
  3: 'push failed',
  4: `branch pushed, but no PR: the base branch ${d.base} is not on origin`,
  5: 'branch pushed, but no PR: gh is missing or not signed in',
}
if (!land) return `${id}: Verify passed and review clean, but the landing step returned nothing. Run \`friday land ${id} --base ${d.base}\` yourself.`
const tail = land.output.trim().split('\n').slice(-3).join(' | ')
const meaning = LAND_MEANING[land.exit_code] || `friday land exited ${land.exit_code}`
return `${id} done: Verify passed, review clean. ${meaning}. ${tail}${land.exit_code ? ` To retry: friday land ${id} --base ${d.base}` : ''}`
