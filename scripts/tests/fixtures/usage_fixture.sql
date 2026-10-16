CREATE TABLE usage(
  uid TEXT PRIMARY KEY,
  ts TEXT,
  day TEXT,
  backend TEXT,
  model TEXT,
  input_tokens INT DEFAULT 0,
  output_tokens INT DEFAULT 0,
  cache_read INT DEFAULT 0,
  cache_write INT DEFAULT 0,
  reasoning INT DEFAULT 0
);
INSERT INTO usage(uid,ts,day,backend,model,input_tokens,output_tokens) VALUES
  ('u1', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'claude', 'claude-sonnet-5', 1000000, 0),
  ('u2', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'codex', 'gpt-5.6-sol', 2000, 500),
  ('u3', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'codex', NULL, 3000, 0),
  ('u4', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'gemini', 'gemini-3.8-flash', 5000, 0),
  ('u5', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'openrouter', 'nvidia/nemotron-3-ultra-550b-a55b:free', 9000, 0),
  ('u6', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'mistral', 'codestral-latest', 7000, 0),
  ('u7', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'mistral', 'ministral-3b-latest', 10, 0),
  ('u8', '2020-01-01 12:00:00', '2020-01-01', 'gemini', 'gemini-old', 999999, 0),
  ('u9', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-1 hour'), date('now','localtime'), 'claude', 'claude-haiku-4-5-20251001', 100, 50),
  ('u10', strftime('%Y-%m-%dT%H:%M:%f+00:00','now','-20 days'), date('now','localtime','-20 days'), 'claude', 'claude-sonnet-5', 500000, 0);
