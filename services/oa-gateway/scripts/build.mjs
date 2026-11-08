import {mkdirSync,copyFileSync,readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
mkdirSync('dist/server',{recursive:true});mkdirSync('dist/.openai',{recursive:true});
copyFileSync('worker/index.js','dist/server/index.js');
copyFileSync('.openai/hosting.json','dist/.openai/hosting.json');
assert.equal(typeof (await import('../worker/index.js')).default.fetch,'function');
assert.ok(JSON.parse(readFileSync('.openai/hosting.json')).project_id);
console.log('Built and validated Worker ESM');
