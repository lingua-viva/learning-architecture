// Lingua Viva Broker Database
// SQLite via better-sqlite3 (sync API, proven)

import Database from 'better-sqlite3';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MIGRATIONS_DIR = join(__dirname, '..', 'migrations');
const CURRENT_SCHEMA_VERSION = '1.0.0';

function getTableSql(db, tableName) {
  const row = db.prepare(`SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?`).get(tableName);
  return row?.sql ?? '';
}

function hasLegacyForeignKeySchema(db) {
  const messagesSql = getTableSql(db, 'messages');
  const gateLogSql = getTableSql(db, 'gate_log');
  return (
    messagesSql.includes('FOREIGN KEY (from_agent) REFERENCES peers(identity)') ||
    messagesSql.includes('FOREIGN KEY (to_agent) REFERENCES peers(identity)') ||
    gateLogSql.includes('FOREIGN KEY (message_id) REFERENCES messages(message_id)')
  );
}

function ensureSchemaMeta(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_meta (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
  `);
  db.prepare(`
    INSERT OR REPLACE INTO schema_meta (key, value, updated_at)
    VALUES (?, ?, ?)
  `).run('schema_version', CURRENT_SCHEMA_VERSION, new Date().toISOString());
}

function migrateLegacyForeignKeySchema(db, migrationSql) {
  const migrate = db.transaction(() => {
    db.pragma('foreign_keys = OFF');
    const hasMessages = !!getTableSql(db, 'messages');
    const hasGateLog = !!getTableSql(db, 'gate_log');
    if (hasGateLog) db.exec('ALTER TABLE gate_log RENAME TO gate_log_legacy');
    if (hasMessages) db.exec('ALTER TABLE messages RENAME TO messages_legacy');
    db.exec(migrationSql);
    if (hasMessages) {
      db.exec(`INSERT INTO messages (message_id, thread_id, in_reply_to, from_agent, to_agent, message_type, intent, risk_level, requires_ack, payload, state, created_at, ttl_seconds, delivered_at, acked_at) SELECT message_id, thread_id, in_reply_to, from_agent, to_agent, message_type, intent, risk_level, requires_ack, payload, state, created_at, ttl_seconds, delivered_at, acked_at FROM messages_legacy`);
      db.exec('DROP TABLE messages_legacy');
    }
    if (hasGateLog) {
      db.exec(`INSERT INTO gate_log (id, message_id, gate_result, rule_triggered, evaluated_at, resolved_at, resolved_by) SELECT id, message_id, gate_result, rule_triggered, evaluated_at, resolved_at, resolved_by FROM gate_log_legacy`);
      db.exec('DROP TABLE gate_log_legacy');
    }
    db.pragma('foreign_keys = ON');
  });
  migrate();
}

export function initDb(dbPath) {
  const db = new Database(dbPath);

  // Run migrations
  for (const file of ['001_initial_schema.sql', '002_broadcast_deliveries.sql', '003_agent_memory.sql', '004_agent_skills.sql', '005_message_search.sql']) {
    db.exec(readFileSync(join(MIGRATIONS_DIR, file), 'utf-8'));
  }

  if (hasLegacyForeignKeySchema(db)) {
    migrateLegacyForeignKeySchema(db, readFileSync(join(MIGRATIONS_DIR, '001_initial_schema.sql'), 'utf-8'));
  }

  // 006: skill enhancements — add columns safely
  const colAlters = [
    ['maturity', 'TEXT', "'UNVALIDATED'"],
    ['shared', 'INTEGER', '0'],
    ['source_agent', 'TEXT', "''"],
    ['tags', 'TEXT', "'[]'"],
    ['last_used_at', 'TEXT', "''"],
  ];
  for (const [col, type, dflt] of colAlters) {
    try {
      db.exec(`ALTER TABLE agent_skills ADD COLUMN ${col} ${type} NOT NULL DEFAULT ${dflt}`);
    } catch { /* column already exists */ }
  }
  db.exec(readFileSync(join(MIGRATIONS_DIR, '006_skill_enhancements.sql'), 'utf-8'));

  // FTS backfill
  const ftsCount = db.prepare(`SELECT COUNT(*) AS c FROM messages_fts`).get().c;
  const msgCount = db.prepare(`SELECT COUNT(*) AS c FROM messages`).get().c;
  if (ftsCount < msgCount) {
    const msgs = db.prepare(`SELECT message_id, from_agent, intent, payload FROM messages`).all();
    const insert = db.prepare(`INSERT OR IGNORE INTO messages_fts(message_id, from_agent, intent, payload_text) VALUES (?, ?, ?, ?)`);
    const tx = db.transaction(() => {
      for (const m of msgs) insert.run(m.message_id, m.from_agent, m.intent, m.payload);
    });
    tx();
  }

  ensureSchemaMeta(db);
  return db;
}
