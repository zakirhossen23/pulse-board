-- Created once by the remix, in the bucket it makes. Natural keys only: DataK3 has no sequences.
CREATE TABLE IF NOT EXISTS boards (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  owner_email TEXT NOT NULL,
  created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memberships (
  id TEXT PRIMARY KEY,            -- board_id + ':' + email
  board_id TEXT NOT NULL,
  email TEXT NOT NULL,
  role TEXT NOT NULL              -- owner | member | viewer
);

CREATE TABLE IF NOT EXISTS cards (
  id TEXT PRIMARY KEY,
  board_id TEXT NOT NULL,
  list_name TEXT NOT NULL,        -- To do | Doing | Done
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  assignee TEXT,
  due_date DATE,
  labels TEXT DEFAULT '[]',       -- JSON array of label strings
  blocked_by TEXT DEFAULT '[]',   -- JSON array of blocker card IDs
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity (
  id TEXT PRIMARY KEY,
  board_id TEXT NOT NULL,
  card_id TEXT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  event_at TIMESTAMP
);
