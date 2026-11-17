export const meta = {
  name: 'execute',
  description: 'Execute one approved friday directive on the goal model: parse it, implement each step on the goal branch, gate on Verify (skipped for external), independent review incl. Acceptance, land by the Land field',
  whenToUse: 'After the user approves a directive in docs/directives/. Pass the directive id, e.g. /friday:execute gm-03',
  phases: [
    { title: 'Prepare', detail: 'friday parse --json, friday start --no-gate (goal branch, order, base); no commit' },
    { title: 'Implement', detail: 'one implementer per step, in order, labelled step n/total' },
    { title: 'Verify', detail: 'run Verify; fix and rerun until it passes or stops making progress (skipped for external)' },
    { title: 'Review', detail: 'independent Opus verifier grades the steps and ## Acceptance over this directive\'s commits' },
    { title: 'Land', detail: 'finish, then by Land: goal push (PR after the last directive), pr, or none' },
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
const PARSE = {
  type: 'object',
  required: ['exit_code', 'stdout'],
  properties: {
    exit_code: { type: 'integer', description: 'exit code of friday parse' },
    stdout: { type: 'string', description: 'its stdout, verbatim' },
  },
}
const START = {
  type: 'object',
  required: ['started', 'output', 'review_base'],
  properties: {
    started: { type: 'boolean', description: 'false if friday start refused' },
    output: { type: 'string', description: 'friday start output verbatim when it refused, else empty' },
    review_base: { type: 'string', description: 'the sha from the `base <sha>` line of friday start' },
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
  required: ['gaps', 'acceptance', 'confidence'],
  properties: {
    acceptance: {
      type: 'array',
      description: 'one entry per ## Acceptance bullet; empty when the directive has none',
      items: {
        type: 'object',
        required: ['item', 'met', 'evidence'],
        properties: { item: { type: 'string' }, met: { type: 'boolean' }, evidence: { type: 'string' } },
      },
    },
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

// Verify/review state known so far, recorded by `friday finish --blocked`.
const state = { verify: '', review: '' }
const q = t => String(t).replace(/\s+/g, ' ').replace(/[`"$\\]/g, "'").trim()

async function block(reason) {
  log(`${id} blocked: ${reason}`)
  const args = [`--blocked "${q(reason)}"`]
  if (state.verify) args.push(`--verify "${q(state.verify)}"`)
  if (state.review) args.push(`--review "${q(state.review)}"`)
  const cmd = `friday finish ${id} ${args.join(' ')}`
  await agent(
    `Directive ${id} has to stop for the user. Run exactly \`${cmd}\` from the repo root and return its exit code and output verbatim. Write no Log text yourself and make no commit yourself (friday finish does). Do not push.`,
    { agentType: 'friday:implementer', schema: LAND, label: 'record block', phase: 'Land' },
  )
  return `${id} is blocked and needs you: ${reason}`
}

// Every reported gap plus every unmet Acceptance item.
function allGaps(r) {
  const gaps = (r && Array.isArray(r.gaps) ? r.gaps : []).map(g => ({ ...g }))
  for (const a of (r && Array.isArray(r.acceptance) ? r.acceptance : [])) {
    if (!a.met) gaps.push({ where: 'Acceptance', problem: `not met: ${a.item}`, evidence: a.evidence })
  }
  return gaps
}

const verifyLineOf = () => `Verify passed: ${String(directiveVerify).replace(/`/g, "'")}`
let directiveVerify = ''

async function verifyLoop(d, label) {
  directiveVerify = d.verify
  let last = '', same = 0
  for (let round = 1; ; round++) {
    const v = await agent(
      `Run the Verify command of friday directive ${id} from the repo root, exactly as written, and wait for it to finish (it can take several minutes):\n\n${d.verify}\n\nReturn whether it passed, its exit code, the first failing test or error line verbatim, and the last 60 lines of output.`,
      { agentType: 'friday:runner', schema: VERIFY, label: `${label} verify ${round}`, phase: 'Verify' },
    )
    if (v && v.passed) { state.verify = verifyLineOf(); return { ok: true, rounds: round } }
    const sig = v ? v.signature : 'the verify run returned nothing'
    same = sig === last ? same + 1 : 1
    last = sig
    if (round >= MAX_FIX_ROUNDS || same >= MAX_SAME_FAILURE) {
      return { ok: false, why: `Verify still fails after ${round} round(s): ${sig}` }
    }
    const fix = await agent(
      `Directive ${id} (${directive}): its Verify command fails.\n\nCommand: ${d.verify}\nFirst failure: ${sig}\nOutput tail:\n${v ? v.tail : '(none)'}\n\nFind and fix the root cause within the directive's scope. Do not weaken, skip or delete tests or checks. Run the failing part again to confirm, then commit (last line \`Directive: ${id}\`).`,
      { agentType: 'friday:implementer', schema: STEP, label: `${label === 'initial' ? '' : label + ' '}fix ${round}/${MAX_FIX_ROUNDS}`, phase: 'Verify' },
    )
    if (fix && fix.status === 'needs_user') return { ok: false, why: fix.question }
  }
}

// ---------------------------------------------------------------- prepare
phase('Prepare')
const parsed = await agent(
  `Run \`friday parse ${id} --json\` from the repo root. Return its exit code and its stdout verbatim (do not summarise or reformat). Change nothing.`,
  { agentType: 'friday:runner', schema: PARSE, label: `parse ${id}`, phase: 'Prepare' },
)
if (!parsed) return `${id} not started: the parse step returned nothing`
let d
try {
  d = JSON.parse(parsed.stdout)
} catch (e) {
  return `${id} not started: friday parse gave invalid JSON (exit ${parsed.exit_code})`
}
if (parsed.exit_code !== 0 || !d || typeof d !== 'object') {
  const errs = d && Array.isArray(d.errors) && d.errors.length ? d.errors.join('; ') : `friday parse exited ${parsed.exit_code}`
  return `${id} not started: ${errs}`
}
if (Array.isArray(d.errors) && d.errors.length) return `${id} not started: ${d.errors.join('; ')}`
if (!(d.status === 'approved' || String(d.status).startsWith('running@'))) {
  return `${id} not started: Status is "${d.status}", not approved`
}

const st = await agent(
  `Start friday directive ${id}. From the repo root:\n1. Run \`friday start ${id} --no-gate\` (it switches to the right branch and enforces goal order). If it refuses (non-zero exit), return started=false with its output verbatim and change nothing else.\n2. Return the sha from the \`base <sha>\` line of its output as review_base.\n3. If the environment variable FRIDAY_DISPATCHED_FROM is set (check with \`printenv FRIDAY_DISPATCHED_FROM\`), append exactly one line \`$(date +%F): Dispatched from <that value> to $(hostname)\` to \`runs/${id}/notes.md\` (create the file and directory if missing; it is untracked). If it is not set, write nothing.\nCommit nothing.`,
  { agentType: 'friday:implementer', schema: START, label: `start ${id}`, phase: 'Prepare' },
)
if (!st) return `${id} not started: the start step returned nothing`
if (!st.started) return `${id} not started: ${st.output}`
d.reviewBase = st.review_base
log(`${id}: ${d.steps.map(s => `${s.n}. ${s.text.slice(0, 60)}`).join(' | ')}`)

// ---------------------------------------------------------------- implement
phase('Implement')
for (const s of d.steps) {
  const opts = { agentType: 'friday:implementer', schema: STEP, label: `step ${s.n}/${d.steps.length}${s.heavy ? ' [heavy]' : ''}`, phase: 'Implement' }
  if (s.heavy) opts.model = 'opus'
  const r = await agent(
    `Implement step ${s.n} of friday directive ${id} (${directive}) on branch ${d.land === 'pr' ? `friday/${id}` : `friday/${d.goal}`}.\n\nStep ${s.n}: ${s.text}\n\nRead the whole directive first (goal, out of scope). Earlier steps are already committed. Prove the step with a focused check. Commit only if you changed tracked files (last line \`Directive: ${id}\`); if the step only reproduces, measures or inspects, append your findings to \`runs/${id}/notes.md\` and do not commit.`,
    opts,
  )
  if (!r) return await block(`step ${s.n} agent did not return`)
  if (r.status === 'needs_user') return await block(`step ${s.n}: ${r.question}`)
  if (r.status === 'failed') return await block(`step ${s.n} failed: ${r.summary}`)
}

// ---------------------------------------------------------------- verify + review
phase('Verify')
const external = d.deliverable === 'external'
let v
if (external) {
  log(`${id}: Verify skipped: Deliverable is external (nothing in this repo to run)`)
  v = { ok: true, rounds: 0 }
  state.verify = 'n/a (external)'
} else {
  v = await verifyLoop(d, 'initial')
  if (!v.ok) return await block(v.why)
}
const accept = Array.isArray(d.acceptance) && d.acceptance.length
  ? `Acceptance bullets (grade each as met or not, with evidence, in the acceptance field):\n${d.acceptance.map(a => `- ${a}`).join('\n')}`
  : 'The directive has no Acceptance bullets; return an empty acceptance array.'
const verifyNote = external ? 'Verify was skipped (Deliverable external).' : 'Its Verify command already passes.'

phase('Review')
let review = await agent(
  `Review friday directive ${id}: read ${directive}, then the change: \`git diff ${d.reviewBase}..HEAD\` and \`git log --oneline ${d.reviewBase}..HEAD\`. ${verifyNote} Deliverable: ${d.deliverable}. Report only gaps that affect correctness or the directive's stated requirements. Every commit message must contain the line \`Directive: ${id}\`, before or after a Co-Authored-By trailer (not necessarily last).\n\n${accept}`,
  { agentType: 'friday:verifier', schema: REVIEW, label: 'verifier', phase: 'Review' },
)
let reviewVerdict = 'no gaps'
if (review && allGaps(review).length) {
  const list = allGaps(review).map((g, i) => `${i + 1}. ${g.where}: ${g.problem} (evidence: ${g.evidence})`).join('\n')
  const fix = await agent(
    `An independent review of directive ${id} (${directive}) found these gaps:\n${list}\n\nFix each one that is real, within scope. If you disagree with one, leave it and explain why with evidence. Commit (last line \`Directive: ${id}\`).`,
    { agentType: 'friday:implementer', schema: STEP, label: 'fix review gaps', phase: 'Review' },
  )
  if (fix && fix.status === 'needs_user') return await block(fix.question)
  if (!external) {
    v = await verifyLoop(d, 'after review')
    if (!v.ok) return await block(v.why)
  }
  review = await agent(
    `Second review of friday directive ${id}. Earlier gaps:\n${list}\n\nRead ${directive} and \`git diff ${d.reviewBase}..HEAD\`. Report only gaps that still affect correctness or the stated requirements. Every commit message must contain the line \`Directive: ${id}\`, before or after a Co-Authored-By trailer (not necessarily last).\n\n${accept}`,
    { agentType: 'friday:verifier', schema: REVIEW, label: 'verifier (2nd)', phase: 'Review' },
  )
  if (review && allGaps(review).length) {
    return await block(`review gaps remain: ${allGaps(review).map(g => `${g.where}: ${g.problem}`).join('; ')}`)
  }
  reviewVerdict = `gaps fixed in second review: ${list.replace(/\n/g, ' ')}`
}
state.review = reviewVerdict

// ---------------------------------------------------------------- land
phase('Land')
const landMode = d.land || 'goal'
const lastLinesOf = o => String(o || '').trim().split('\n').slice(-3).join(' | ')
const verifyLine = external ? 'Verify: n/a (external)' : `Verify passed: ${String(d.verify).replace(/`/g, "'")}`
const branch = landMode === 'pr' ? `friday/${id}` : `friday/${d.goal}`
const gdirs = Array.isArray(d.goal_directives) ? d.goal_directives : []
const isLast = landMode === 'goal' && d.position != null && d.position === gdirs.length
const nextId = landMode === 'goal' && d.position != null && d.position < gdirs.length ? gdirs[d.position].id : ''
const landCmd = landMode === 'pr' ? `friday land ${id} --base ${d.base}` : `friday land ${id}`

const finishCmd = `friday finish ${id} --verify "${q(state.verify || verifyLine)}" --review "${q(reviewVerdict)}"`
const finish = await agent(
  `Close out friday directive ${id} from the repo root, on branch ${branch}. Run exactly \`${finishCmd}\` and return its exit code and its output verbatim. Write no Log text yourself and make no commit yourself (friday finish does both). Do not push.`,
  { agentType: 'friday:implementer', schema: LAND, label: 'finish', phase: 'Land' },
)
if (!finish || finish.exit_code !== 0) return await block(`could not finish: ${finish ? lastLinesOf(finish.output) : 'the agent returned nothing'}`)

const runLand = (cmd, label) => agent(
  `Run exactly \`${cmd}\` from the repo root, on branch ${branch} (it pushes and may open a PR; do not push or call gh yourself). If it needs a permission, ask for it; do not work around it. Return its exit code and its output verbatim.`,
  { agentType: 'friday:implementer', schema: LAND, label, phase: 'Land' },
)
const lastLines = o => String(o || '').trim().split('\n').slice(-3).join(' | ')
const LAND_MEANING = {
  0: 'PR open',
  3: 'push failed',
  4: `branch pushed, but no PR: the base branch ${d.base} is not on origin`,
  5: 'branch pushed, but no PR: gh is missing or not signed in',
  6: 'not pushed: a directive Verify failed on the goal branch',
}
const head = `${id} done: ${external ? 'Verify n/a (external)' : 'Verify passed'}, review clean.`

if (landMode === 'none') return `${head} Land none: committed only, nothing pushed.`

const land = await runLand(landCmd, 'land')
if (!land) return `${head} The landing step returned nothing. Run \`${landCmd}\` yourself.`

if (landMode === 'pr') {
  const meaning = LAND_MEANING[land.exit_code] || `friday land exited ${land.exit_code}`
  return `${head} ${meaning}. ${lastLines(land.output)}${land.exit_code ? ` To retry: ${landCmd}` : ''}`
}

// Land goal
if (land.exit_code !== 0) {
  return `${head} ${LAND_MEANING[land.exit_code] || `friday land exited ${land.exit_code}`}. ${lastLines(land.output)} To retry: ${landCmd}`
}
if (!isLast) {
  return `${head} Pushed ${branch}; next: /friday:execute ${nextId || '(none)'}`
}
const goalCmd = `friday land --goal ${d.goal}`
const gl = await runLand(goalCmd, 'land goal')
if (!gl) return `${head} Pushed ${branch}, but the goal landing step returned nothing. Run \`${goalCmd}\` yourself.`
const gm = LAND_MEANING[gl.exit_code] || `friday land --goal exited ${gl.exit_code}`
return `${head} Last directive of goal ${d.goal}: pushed ${branch}. ${gm}. ${lastLines(gl.output)}${gl.exit_code ? ` To retry: ${goalCmd}` : ''}`
