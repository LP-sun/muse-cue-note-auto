import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, symlink, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { isWithin, strictPath, newPlanFolder, runCli, briefPlan } from '../runtime.js';

test('root containment rejects traversal or symlink escape', async () => {
  const base = await mkdtemp(join(tmpdir(), 'cue-root-'));
  const outside = await mkdtemp(join(tmpdir(), 'cue-out-'));
  const outsideFile = join(outside,'evil.mscz'); await writeFile(outsideFile,'test');
  const inside = join(base,'good.mscz'); await writeFile(inside,'test');
  assert.equal(await strictPath(inside,base,'score'),inside);
  await assert.rejects(strictPath(outsideFile,base,'score'),/outside/);
  await symlink(outsideFile, join(base,'alias.mscz'));
  await assert.rejects(strictPath('alias.mscz',base,'score'),/outside/);
  assert.equal(isWithin(inside,base),true);
});

test('unique review folder is beneath root', async () => {
  const base=await mkdtemp(join(tmpdir(),'cue-root-'));
  const a=await newPlanFolder(base), b=await newPlanFolder(base);
  assert.notEqual(a,b); assert.equal(isWithin(a,base),true);
});

test('Python read-only CLI runs from plugin directory', async () => {
  const path=join(import.meta.dirname,'..','..','examples','demo-orchestra.mscz');
  const result=await runCli('python3',['analyze',path,'--min-rest','8']);
  assert.ok(Array.isArray(result.candidates)); assert.ok(result.candidates.length>0);
  const preview=briefPlan(result);assert.ok(preview.sample.length>0);
});
