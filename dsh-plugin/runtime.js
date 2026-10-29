import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, readFile, realpath } from 'node:fs/promises';
import { join, resolve, relative, isAbsolute, extname, basename } from 'node:path';
import { randomUUID } from 'node:crypto';

export function isWithin(file, root) {
  const r = relative(root, file);
  return r === '' || (r !== '..' && !r.startsWith('../') && !r.startsWith('..\\') && !isAbsolute(r));
}

export async function strictPath(raw, root, type='file') {
  if (typeof raw !== 'string' || !raw.trim()) throw new Error('Input path is required');
  const base = await realpath(root);
  const target = await realpath(isAbsolute(raw) ? raw : resolve(base, raw));
  if (!isWithin(target, base)) throw new Error('Path is outside configured scores root');
  if (type === 'score' && !['.mscx', '.mscz'].includes(extname(target).toLowerCase())) {
    throw new Error('Expected .mscx or .mscz score');
  }
  if (type === 'plan' && !target.toLowerCase().endsWith('.cue-plan.json')) {
    throw new Error('Expected a generated .cue-plan.json');
  }
  return target;
}

export async function newPlanFolder(root) {
  const base = await realpath(root);
  const dest = join(base, 'CuePlans');
  await mkdir(dest, { recursive: true });
  if (!isWithin(await realpath(dest), base)) throw new Error('CuePlans points outside root');
  return await mkdtemp(join(dest, 'run-'));
}

export function safePython(python='python3') {
  if (process.platform === 'win32') {
    if (python === 'py') return { bin: 'py', prefix: ['-3'] };
    if (python === 'python3') return { bin: 'python', prefix: [] };
  }
  return { bin: python, prefix: [] };
}

// Non-shell Python execution, bounded I/O and time. The score is never modified.
export function runCli(python, argv, { signal, timeoutMs=120_000 }={}) {
  const {bin, prefix} = safePython(python);
  return new Promise((resolvePromise, reject) => {
    const command = [...prefix, '-m', 'cueplanner', ...argv];
    const projectRoot = resolve(import.meta.dirname);
    let done = false, out = '', err = '';
    const child = spawn(bin, command, {
      cwd: projectRoot, shell: false, windowsHide: true, stdio: ['ignore','pipe','pipe'],
      env: { ...process.env, PYTHONPATH: [projectRoot, process.env.PYTHONPATH || ''].filter(Boolean).join(process.platform === 'win32' ? ';' : ':') }
    });
    const finish = (error, value) => {
      if (done) return; done = true; clearTimeout(timer);
      if (signal) signal.removeEventListener('abort', abort);
      if (error) reject(error); else resolvePromise(value);
    };
    const abort = () => { child.kill(); finish(new Error('Cue operation aborted')); };
    const timer = setTimeout(() => { child.kill(); finish(new Error('Cue operation timed out')); }, timeoutMs);
    if (signal) { if (signal.aborted) return abort(); signal.addEventListener('abort', abort, { once: true }); }
    child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
    child.stdout.on('data', s => { out+=s; if(out.length>2_000_000){child.kill();finish(new Error('Cue output too large'));} });
    child.stderr.on('data', s => { err+=s; if(err.length>50_000){child.kill();finish(new Error('Cue error output too large'));} });
    child.on('error', e => finish(e));
    child.on('close', code => {
      if (done) return;
      if (code !== 0) return finish(new Error(`Cue CLI error (exit ${code}): ${err.slice(-3000)}`));
      try { finish(null, JSON.parse(out)); }
      catch { finish(new Error(`Cue CLI returned invalid JSON: ${out.slice(0,200)}`)); }
    });
  });
}

export async function readPlan(planPath, root) {
  const path = await strictPath(planPath, root, 'plan');
  const text = await readFile(path, 'utf8');
  if (text.length > 4_000_000) throw new Error('Cue plan exceeds size limit');
  const plan = JSON.parse(text);
  if (!Array.isArray(plan.candidates)) throw new Error('Invalid cue plan schema');
  return { path, plan };
}

export function briefPlan(plan, max=12) {
  return { source: plan.source, title: plan.title, measure_count: plan.measure_count,
    part_count: plan.part_count, staff_count: plan.staff_count,
    candidate_count: plan.candidates.length, warnings: plan.warnings,
    sample: plan.candidates.slice(0,max).map(c => ({
      id:c.id, target:c.target, entry_measure:c.entry_measure, cue_from:c.cue_from,
      cue_to:c.cue_to, source:c.sources?.[0]?.source,
      source_score:c.sources?.[0]?.score,
      source_risks:c.sources?.[0]?.risk_flags
    })) };
}
