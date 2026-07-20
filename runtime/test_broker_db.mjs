import { initDb } from './broker/db.mjs';
import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

console.log('Engine: better-sqlite3');

const tmp = mkdtempSync(join(tmpdir(), 'lv-runtime-test-'));
const db = await initDb(join(tmp, 'lv.db'));
const now = new Date().toISOString();

db.prepare('INSERT OR REPLACE INTO peers (identity, agent_name, runtime, pid, cwd, git_root, capabilities, palette_role, trust_tier, version, registered_at, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').run(
  'claude.analysis', 'Claude Code', 'node', process.pid, process.cwd(), '/lingua-viva',
  JSON.stringify(['research', 'decide', 'reflect']), 'analyst', '2', '1.0.0', now, now
);
db.prepare('INSERT INTO messages (message_id, from_agent, to_agent, message_type, intent, risk_level, requires_ack, payload, state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').run(
  'msg-001', 'claude.analysis', 'all', 'informational', 'Runtime test', 'none', '0',
  JSON.stringify({content: 'Lingua Viva broker is live'}), 'pending', now
);
db.prepare('INSERT OR REPLACE INTO agent_memory (identity, store, entry_id, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)').run(
  'claude.analysis', 'memory', '1', 'The path through the map IS the memory.', now, now
);
db.prepare('INSERT OR REPLACE INTO agent_skills (identity, skill_name, description, procedure, maturity, shared, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)').run(
  'claude.analysis', 'serial-synthesis', 'Parallel exploration, serial synthesis',
  'Read -> hold -> produce', 'VALIDATED', '1', now, now
);

const peers = db.prepare('SELECT COUNT(*) as c FROM peers').get();
const msgs = db.prepare('SELECT COUNT(*) as c FROM messages').get();
const mem = db.prepare('SELECT content FROM agent_memory WHERE identity = ?').get('claude.analysis');
const skills = db.prepare('SELECT skill_name, maturity FROM agent_skills WHERE identity = ?').all('claude.analysis');

console.log(`Peers:     ${peers.c}`);
console.log(`Messages:  ${msgs.c}`);
console.log(`Memory:    ${mem.content}`);
console.log(`Skills:    ${skills.map(s => s.skill_name + '(' + s.maturity + ')').join(', ')}`);

console.log('');
console.log('Runtime broker DB: ALL PASS');
db.close();
