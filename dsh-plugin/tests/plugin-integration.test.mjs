import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, copyFile, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

// Local mock of defineTool for checking registration/execution only, not a
// claim of a real running DSH host.
test('DSH tool definitions register and offline handlers run with mocked framework', async () => {
  const source = join(import.meta.dirname,'..');
  const temp = await mkdtemp(join(tmpdir(),'cue-dsh-mock-'));
  const index = (await readFile(join(source,'index.js'),'utf8'))
    .replace("import { defineTool } from '@deepseek-ai/dsh-tools';",'const defineTool = x => x;');
  await writeFile(join(temp,'index.mjs'),index);
  await copyFile(join(source,'runtime.js'),join(temp,'runtime.js'));
  await symlink(join(source,'cueplanner'),join(temp,'cueplanner'));
  const fixture = join(source,'..','examples','demo-orchestra.mscz');
  const score = join(temp,'sample.mscz'); await copyFile(fixture,score);
  const before=createHash('sha256').update(await readFile(score)).digest('hex');
  const plugin=await import(pathToFileURL(join(temp,'index.mjs')).href);
  const map=new Map();
  plugin.apply({tools:{register:t=>map.set(t.name,t)}},{root:temp,python:'python3'});
  assert.deepEqual([...map.keys()].sort(), [
    'musescore_cue_analyze','musescore_cue_batch','musescore_cue_candidate',
    'musescore_cue_bridge_check','musescore_cue_focus','musescore_cue_live_verify'
  ].sort());
  const analyzed=JSON.parse(await map.get('musescore_cue_analyze').execute({score}));
  assert.ok(analyzed.candidate_count>0);
  const candidate=JSON.parse(await map.get('musescore_cue_candidate').execute({
    plan:analyzed.plan_path,candidate_id:analyzed.sample[0].id}));
  assert.ok(candidate.candidate.sources.length>=1);
  const after=createHash('sha256').update(await readFile(score)).digest('hex');
  assert.equal(after,before);
  await assert.rejects(map.get('musescore_cue_analyze').execute({score:'/tmp/invalid.mscz'}),
    /ENOENT|outside/);
});
