"""Deterministic local MCP stdio fixture; NOT mcp-score itself."""
import json
import sys

for line in sys.stdin:
    if not line.strip():
        continue
    req = json.loads(line)
    method = req['method']
    if 'id' not in req:
        continue
    ident = req['id']
    if method == 'initialize':
        result = {'protocolVersion':'2025-06-18', 'capabilities':{'tools':{}},
                  'serverInfo':{'name':'fake-mcp-score','version':'test'}}
    elif method == 'tools/list':
        result = {'tools':[{'name':n,'inputSchema':{'type':'object'}} for n in
            ('connect_to_musescore','ping_score_app','get_live_score_info','get_measure_content')]}
    elif method == 'tools/call':
        name = req['params']['name']
        params = req['params']['arguments']
        if name == 'connect_to_musescore':
            obj = {'application':'musescore','uri':f'ws://localhost:{params["port"]}'}
        elif name == 'ping_score_app':
            obj = {'application':'musescore'}
        elif name == 'get_live_score_info':
            obj = {'title':'Cue Test Suite', 'measure_count':12, 'part_count':3,
                   'parts':[{'name':'Oboe'}, {'name':'Clarinet in B♭'}, {'name':'Flute'}]}
        elif name == 'get_measure_content':
            obj = {'measure':params['measure'],'staff':params['staff']}
        else:
            print(json.dumps({'jsonrpc':'2.0', 'id':ident,
                              'result':{'isError':True, 'content':[{'type':'text','text':'unknown tool'}]}}), flush=True)
            continue
        result = {'content':[{'type':'text','text':json.dumps(obj)}], 'isError':False}
    else:
        print(json.dumps({'jsonrpc':'2.0', 'id':ident, 'error':{'code':-32601, 'message':'Unknown method'}}), flush=True)
        continue
    print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result}), flush=True)
