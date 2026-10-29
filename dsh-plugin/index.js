import { defineTool } from '@deepseek-ai/dsh-tools';
import { join, resolve } from 'node:path';
import { strictPath, newPlanFolder, runCli, readPlan, briefPlan } from './runtime.js';

export const name = 'musescore-cue-planner';
export const inject = ['tools'];
const output = {
  schema: { type: 'string' },
  render: (_args, value) => [{ type:'text', text:value }],
};
const json = value => JSON.stringify(value, null, 2);

export function apply(ctx, config={}) {
  const root = resolve(config.root || process.env.DSH_CUE_SCORE_ROOT || process.cwd());
  const python = config.python || (process.platform === 'win32' ? 'py' : 'python3');
  const mcpExe = config.mcpExe || 'mcp-score';
  const port = Number(config.mcpPort ?? 8765);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid MCP Score Bridge port');
  const bridgeArgs = ['--mcp-exe', mcpExe, '--host', 'localhost', '--port', String(port)];
  const settingsArgs = args => [
    '--min-rest', String(args.min_rest ?? 8),
    '--cue-bars', String(args.cue_bars ?? 2),
    '--top-sources', String(args.top_sources ?? 4),
    ...(args.same_transposition_only ? ['--same-transposition-only'] : [])
  ];
  const execCli = (argv, exec, options={}) => runCli(python, argv, { signal:exec?.signal, ...options });
  // No score modification tools are registered in v0.3.
  ctx.tools.register(defineTool({
    name: 'musescore_cue_analyze',
    description: 'Read-only Cue analysis of a SAVED MuseScore 4 MSCZ/MSCX score. Find >=N-bar instrument rests before re-entry and rank possible cues. Writes a JSON and Markdown review plan; does NOT modify original score. Review all suggestions before engraving.',
    parameters: {
      score: { type:'string', required:true, description:'Score file within configured allowed root' },
      min_rest: { type:'integer', description:'Minimum rest bars; 2..128, default 8' },
      cue_bars: { type:'integer', description:'Cue bars before re-entry; 1..4, default 2' },
      top_sources: { type:'integer', description:'Max alternative source instruments; 1..10, default 4' },
      same_transposition_only: { type:'boolean', description:'Exclude sources with differing instrument transposition' }
    }, output,
    async execute(args, exec) {
      const score = await strictPath(args.score, root, 'score');
      const folder = await newPlanFolder(root);
      const planPath = join(folder, 'analysis.cue-plan.json');
      const reportPath = join(folder, 'analysis.cue-review.md');
      const status = await execCli(['analyze', score, ...settingsArgs(args), '--output', planPath, '--markdown', reportPath], exec);
      const { plan } = await readPlan(planPath, root);
      return json({ status:'analysis_complete_review_only', plan_path:planPath, report_path:reportPath,
        stats:status.stats, ...briefPlan(plan), note:'No score changed. Source ranking is heuristic.' });
    }
  }));

  ctx.tools.register(defineTool({
    name:'musescore_cue_batch',
    description:'Analyze MSCZ/MSCX files in one local directory (read-only, no score changes), save separate JSON Cue review plans.',
    parameters:{
      folder:{ type:'string', required:true, description:'Folder within configured allowed scores root' },
      min_rest:{type:'integer'}, cue_bars:{type:'integer'}, top_sources:{type:'integer'},
      limit:{type:'integer',description:'Max score files; 1..1000, default 100'},
      same_transposition_only:{type:'boolean'}
    }, output,
    async execute(args,exec) {
      const folder = await strictPath(args.folder,root,'directory');
      const outDir = await newPlanFolder(root);
      return json({ status:'batch_analysis_complete_review_only', out_dir:outDir,
        ...await execCli(['batch',folder,...settingsArgs(args),'--limit',String(args.limit??100),'--out-dir',outDir],exec) });
    }
  }));

  ctx.tools.register(defineTool({
    name:'musescore_cue_candidate',
    description:'Read one candidate from an existing Cue JSON review plan, including alternative source rankings and risks. Read-only.',
    parameters:{
      plan:{type:'string',required:true,description:'Existing .cue-plan.json within allowed root'},
      candidate_id:{type:'string',required:true,description:'Candidate id, e.g. 5@58'}
    },output,
    async execute(args) {
      const {plan} = await readPlan(args.plan,root);
      const choice = plan.candidates.find(c=>c.id===args.candidate_id);
      if (!choice) throw new Error('Unknown cue candidate id');
      return json({title:plan.title,source:plan.source,candidate:choice,
        warning:'Human assessment required. No Cue has been inserted.'});
    }
  }));

  ctx.tools.register(defineTool({
    name:'musescore_cue_bridge_check',
    description:'Test mcp-score MCP stdio -> local MuseScore Studio MCP Score Bridge connection and report currently open score metadata. Does not modify score.',
    parameters:{},output,
    async execute(_args,exec) {
      return json({status:'bridge_checked',...await execCli(['bridge-check',...bridgeArgs],exec,{timeoutMs:35_000})});
    }
  }));

  ctx.tools.register(defineTool({
    name:'musescore_cue_live_verify',
    description:'Compare a saved MSCZ/MSCX score to the open MuseScore score metadata via local mcp-score. Title/bar/part match does NOT prove file identity. Read-only.',
    parameters:{ score:{type:'string',required:true} },output,
    async execute(args,exec){
      const score=await strictPath(args.score,root,'score');
      return json(await execCli(['live-verify',score,...bridgeArgs],exec,{timeoutMs:35_000}));
    }
  }));

  ctx.tools.register(defineTool({
    name:'musescore_cue_focus',
    description:'Select a reviewed Cue measure in OPEN MuseScore via mcp-score (selection only; no note changes). Requires matching metadata, saved file, and human checking open score identity.',
    parameters:{
      score:{type:'string',required:true},
      candidate_id:{type:'string',required:true,description:'Candidate ID from currently generated analysis'},
      at:{type:'string',description:'cue or entry; default cue'}
    },output,
    async execute(args,exec) {
      if (args.at && !['cue','entry'].includes(args.at)) throw new Error('at must be cue or entry');
      const score=await strictPath(args.score,root,'score');
      return json(await execCli(['focus',score,'--candidate',args.candidate_id,
        '--at',args.at||'cue',...bridgeArgs],exec,{timeoutMs:45_000}));
    }
  }));
}
