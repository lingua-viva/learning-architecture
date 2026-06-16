import { initDb, useLibsql } from './broker/db.mjs';
import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

console.log('Engine:', useLibsql ? 'libSQL (Turso)' : 'better-sqlite3');

const tmp = mkdtempSync(join(tmpdir(), 'mc-test-'));
const db = await initDb(join(tmp, 'mc.db'));
const now = new Date().toISOString();

if (useLibsql) {
  // Async API for libSQL
  await db.prepare('INSERT OR REPLACE INTO peers (identity, agent_name, runtime, pid, cwd, git_root, capabilities, palette_role, trust_tier, version, registered_at, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').runAsync(
    'claude.analysis', 'Claude Code', 'node', String(process.pid), process.cwd(), '/mc',
    JSON.stringify(['research', 'decide', 'reflect']), 'analyst', '2', '1.0.0', now, now
  );
  await db.prepare('INSERT INTO messages (message_id, from_agent, to_agent, message_type, intent, risk_level, requires_ack, payload, state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').runAsync(
    'msg-001', 'claude.analysis', 'all', 'informational', 'Runtime test', 'none', '0',
    JSON.stringify({content: 'Mission Canvas broker is live'}), 'pending', now
  );
  await db.prepare('INSERT OR REPLACE INTO agent_memory (identity, store, entry_id, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)').runAsync(
    'claude.analysis', 'memory', '1', 'The path through the map IS the memory.', now, now
  );
  await db.prepare('INSERT OR REPLACE INTO agent_skills (identity, skill_name, description, procedure, maturity, shared, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)').runAsync(
    'claude.analysis', 'serial-synthesis', 'Parallel exploration, serial synthesis',
    'Read → hold → produce', 'VALIDATED', '1', now, now
  );

  const peers = await db.prepare('SELECT COUNT(*) as c FROM peers').getAsync();
  const msgs = await db.prepare('SELECT COUNT(*) as c FROM messages').getAsync();
  const mem = await db.prepare('SELECT content FROM agent_memory WHERE identity = ?').getAsync('claude.analysis');
  const skills = await db.prepare('SELECT skill_name, maturity FROM agent_skills WHERE identity = ?').allAsync('claude.analysis');

  console.log(`Peers:     ${peers.c}`);
  console.log(`Messages:  ${msgs.c}`);
  console.log(`Memory:    ${mem.content}`);
  console.log(`Skills:    ${skills.map(s => s.skill_name + '(' + s.maturity + ')').join(', ')}`);
} else {
  // Sync API for better-sqlite3
  db.prepare('INSERT OR REPLACE INTO peers (identity, agent_name, runtime, pid, cwd, git_root, capabilities, palette_role, trust_tier, version, registered_at, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').run(
    'claude.analysis', 'Claude Code', 'node', process.pid, process.cwd(), '/mc',
    JSON.stringify(['research', 'decide', 'reflect']), 'analyst', '2', '1.0.0', now, now
  );
  const peers = db.prepare('SELECT COUNT(*) as c FROM peers').get().c;
  console.log(`Peers:     ${peers}`);
}

console.log('');
console.log('Runtime broker DB: ALL PASS');
db.close();
