Scope; 2026-09-05; astra CSO. Relational dispatch graph/ledger/control plane. 3NF REQUIRED; BCNF not target. Scope artifact, no runtime implementation/cutover. SQLite via Python stdlib sqlite3; no ORM, graph DB, extension or model-built runtime graph. Sources read: CONTEXT.md; docs/DECISIONS.md tail80; docs/governance/ASSESSMENT.md; specs/002-dispatch-graph-ledger/spec.md; workerbees/{ledger,control,envelope,registry}.py; workerbees/{governance,protocols}.json. Assessment historical; inspected code wins on current behavior. Additional policy/gateway symbol scan checks reason-code semantics.

Contract. One DB/workspace. run groups top-level brief/preflight; family groups one fan-out, multiple families/run permitted. Labels descriptive. Legacy import creates one explicitly synthetic family/run; cannot recover original fan-out boundaries. request records intent/attempt identity; node records invocation attempt only after dispatch admission. Denied intent has request/decision, no fake node. Dispatch event alone does not prove provider call happened; crash gap leaves usage unknown. run.outcome records acceptance outcome, not scheduler state. Runner remains execution authority; node_event is append-only observed state, node_state/node_usage derived views. No duplicate stored status/cost rollups.

Graph. lineage=authenticated spawn child→parent; graph_edge=reviews/corrects/probes/depends-on child→target; legacy_parent=002 single-parent projection, including parentless probe type. Review parent never implies spawn parent. Root actor may sit outside recorded family; trusted writer attests family root set before depth gating. No lineage rows in legacy import means unknown spawn history. New edges same family; writer rejects cycles on lineage/dependency relations. Review topology is not spawn authority. node_artifact binds produced/source/candidate outputs; edge_artifact binds exact reviewed/corrected content. Reviewer of corrected candidate must reference corrected node/artifact; preserve old edge separately. Unknown old artifact binding stays absent, cannot satisfy strict review gate.

Identity. vendor=model maker; provider=transport/broker. Neither determines the other. route(provider,route_name,revision) freezes alias resolution to model; model/vendor unknown when historic resolution unavailable. Never infer vendor from broker alias. Registry identity differs from invocation/model identity. snapshot freezes three exact config byte streams; governance_document separates governance bytes→version metadata. agent/capability/relationships snapshot-scoped. decision_identity records trusted sender/recipient separately from envelope claims; only captured trusted context qualifies.

Envelope. envelope_identity retains known canonical hash without invented body. envelope optionally decomposes captured wire claims, keyed hash; competing same-message bodies allowed for conflict evidence. task_id does not determine claimed parent_task_id; protocol does not determine claimed schema. Required artifacts and checked/approval rules use ordinal rows, preserving order/duplicates. artifact.sha256→size; kind/role belong to occurrence, not content. envelope_field stores allowlisted scalar leaves (section, RFC6901 pointer, type, value), never JSON containers or credentials. Policy-relevant supported fields get explicit typed validation; do not infer arbitrary cross-field FDs. Payload/complete schema documents remain opaque protected content artifacts, not control facts hidden in JSON columns. Raw retained envelope may contain confidential payload; existing access/retention rules apply outside DB. Authentication material never copied into schema or prompts.

3NF proof contract. For every nontrivial X→A in stated FD closure: X superkey OR A prime. 1NF: scalar domains; no repeating lists. Catalog below states complete semantic generating FDs per base relation; “rest” means remaining DDL columns, “key” means listed full K. Proof uses these FDs and their closure, not surrogate-key existence alone. Version strings/timestamps are labels, not identifiers; no governance_version→bytes assumption. Same version may label distinct edited files. Family label not unique; relationship_type alone determines no parameters; agent_id alone determines no snapshot metadata. Reason-code verdict immutable; changed semantics needs new code. Import source identifies ingestion attempt, so repeated source bytes allowed. Nullable fields represent missing observations; do not replace with zero/sentinel. Nullable alternate uniqueness applies only populated tuples; nonnull primary keys remain full-relation identities. No FD makes model/provider global aliases interchangeable. Views may repeat derived attributes; excluded from stored-table proof.

3NF versus BCNF. No evidenced base relation here requires prime-RHS exception; tables incidentally satisfy BCNF under stated FDs. This is no BCNF mandate. Do not introduce extra decomposition merely to reach BCNF. Actual 3NF repairs: node_id→family→run removed from reservations/decisions; route→model→vendor removed from nodes; governance_sha→version metadata removed from snapshot; reason_code→allowed removed from decision. Constant hard-$0/unsupported-cap flags omitted from per-run rows; otherwise empty-set→constant creates redundant nonprime FDs.

Divergence, conditional only: R(family,role,agent), FDs family+role→agent and agent→role. Candidate keys family+role and family+agent; all attributes prime. agent→role allowed by 3NF, rejected by BCNF because agent not superkey. Lossless split (agent,role)+(family,agent) loses dependency-preserving enforcement of family+role→agent; needs join check. CEO keeps 3NF to preserve such constraints locally if real business rules later justify them. Example NOT adopted: actual multi-capability/versioned registry proves no agent→single-role FD. Inventing a violation would misstate domain.

vendor K=vendor_id. Single column; trivial FDs only; 3NF.

provider K=provider_id. Single column; trivial FDs only; 3NF.

envelope_identity K=envelope_hash. Single column; trivial FDs only; 3NF.

model K=model_id; known-vendor alternate K=(vendor_id,model_name). FDs: each key->rest. Unknown-vendor rows rely on model_id; SQL nullable UNIQUE is not a global candidate key. No further nontrivial FD; 3NF.

route K: route_id. FDs: route_id->rest, provider_id,route_name,revision->rest. 3NF: every stated determinant candidate key.

artifact K: sha256. FDs: sha256->size_bytes. 3NF: only stated nontrivial determinant is key.

governance_document K: governance_sha. FDs: governance_sha->governance_version,policy_version. 3NF: only stated nontrivial determinant is key.

snapshot K: snapshot_hash. FDs: snapshot_hash->rest, governance_sha,protocols_sha,routing_sha->rest. 3NF: every stated determinant candidate key.

agent K: snapshot_hash,agent_id. FDs: snapshot_hash,agent_id->rest. 3NF: only stated nontrivial determinant is full key.

capability K: snapshot_hash,capability_id. FDs: none (trivial). 3NF: all-key relation.

agent_capability K: snapshot_hash,agent_id,capability_id. FDs: none (trivial). 3NF: all-key relation.

relationship K: snapshot_hash,source_id,target_id,relationship_type. FDs: snapshot_hash,source_id,target_id,relationship_type->max_depth,requires_approval. 3NF: only stated nontrivial determinant is full key.

relationship_param K: snapshot_hash,source_id,target_id,relationship_type,ordinal. FDs: key->value. 3NF: only stated nontrivial determinant is full key.

run K: run_id. FDs: run_id->created_at,outcome. 3NF: only stated nontrivial determinant is key.

run_budget K: run_id. FDs: run_id->max_calls,max_seconds. 3NF: only stated nontrivial determinant is key.

family K: family_id. FDs: family_id->run_id,label. 3NF: only stated nontrivial determinant is key.

envelope K: envelope_hash. FDs: envelope_hash->message_id,task_id,parent_task_id,correlation_id,sender,recipient,intent,operation,protocol,schema_name,classification,created_at,expires_at,deadline,reply_to,payload_sha. 3NF: only stated nontrivial determinant is key.

envelope_artifact K: envelope_hash,ordinal. FDs: key->sha256,kind. 3NF: only stated nontrivial determinant is full key.

envelope_field K: envelope_hash,section,pointer. FDs: key->type,value. 3NF: only stated nontrivial determinant is full key.

request K: request_id. FDs: request_id->family_id,envelope_hash. 3NF: only stated nontrivial determinant is key.

node K: node_id. FDs: node_id->route_id,tier,task,created_at. 3NF: only stated nontrivial determinant is key.

node_event K: event_id. FDs: event_id->rest, node_id,event_seq->rest. 3NF: every stated determinant candidate key.

usage K: event_id. FDs: event_id->seconds,subscription_calls,input_tokens,output_tokens,reasoning_tokens,cost_micro_usd. 3NF: only stated nontrivial determinant is key.

lineage K: child_id. FDs: child_id->parent_id. 3NF: only stated nontrivial determinant is key.

graph_edge K: source_id,target_id,edge_type. FDs: none (trivial). 3NF: all-key relation.

legacy_parent K: child_id. FDs: child_id->parent_id,edge_type. 3NF: only stated nontrivial determinant is key.

edge_artifact K: source_id,target_id,edge_type,ordinal. FDs: key->sha256,role. 3NF: only stated nontrivial determinant is full key.

frontier_gate K: node_id. FDs: node_id->reason. 3NF: only stated nontrivial determinant is key.

decision_code K: reason_code. FDs: reason_code->allowed. 3NF: only stated nontrivial determinant is key.

decision K: decision_id. FDs: decision_id->request_id,reason_code,reason,policy_version,created_at. 3NF: only stated nontrivial determinant is key.

decision_snapshot K: decision_id. FDs: decision_id->snapshot_hash. 3NF: only stated nontrivial determinant is key.

decision_rule K: decision_id,ordinal. FDs: key->rule_id. 3NF: only stated nontrivial determinant is full key.

reservation K: request_id. FDs: request_id->calls,seconds,released,created_at. 3NF: only stated nontrivial determinant is key.

replay K: message_id. FDs: message_id->rest, envelope_hash->rest. 3NF: every stated determinant candidate key.

cancellation K: run_id. FDs: run_id->at. 3NF: only stated nontrivial determinant is key.

lease K: workspace_key. FDs: workspace_key->run_id,acquired_at. 3NF: only stated nontrivial determinant is key.

approval K: approval_id. FDs: approval_id->run_id,requester,action,resource,artifact_hash,risk,expires_at,approver,decision,decided_at. 3NF: only stated nontrivial determinant is key.

approval_rule K: approval_id,ordinal. FDs: key->rule_id. 3NF: only stated nontrivial determinant is full key.

import_source K: source_id. FDs: source_id->kind,source_sha. 3NF: only stated nontrivial determinant is key.

import_issue K: source_id,record_no,code. FDs: key->detail. 3NF: only stated nontrivial determinant is full key.

decision_identity K=decision_id. FD: decision_id->authenticated_sender_id,recipient_id. Only stated nontrivial determinant key; 3NF.

node_artifact K=(node_id,sha256,role). All attributes prime; stated FDs trivial only; 3NF.

DDL. Execute first four SQL blocks as one sqlite3.executescript on fresh staging DB; later q1–q5 blocks are parameterized SELECTs. Every connection PRAGMA foreign_keys=ON before transaction. SQL checks/FKs cover declared row constraints; writer obligations below cover cross-row semantics, type strictness and immutability. No claim DDL alone implements complete control plane.


```sql
PRAGMA foreign_keys = ON;
CREATE TABLE vendor (vendor_id TEXT PRIMARY KEY NOT NULL);
CREATE TABLE provider (provider_id TEXT PRIMARY KEY NOT NULL);
CREATE TABLE model (
  model_id TEXT PRIMARY KEY NOT NULL,
  vendor_id TEXT REFERENCES vendor(vendor_id), model_name TEXT NOT NULL,
  UNIQUE (vendor_id, model_name)
);
CREATE TABLE route (
  route_id TEXT PRIMARY KEY NOT NULL,
  provider_id TEXT NOT NULL REFERENCES provider(provider_id),
  route_name TEXT NOT NULL, revision INTEGER NOT NULL,
  model_id TEXT REFERENCES model(model_id),
  UNIQUE (provider_id, route_name, revision)
);
CREATE TABLE artifact (
  sha256 TEXT PRIMARY KEY NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0)
);
CREATE TABLE governance_document (
  governance_sha TEXT PRIMARY KEY NOT NULL REFERENCES artifact(sha256),
  governance_version TEXT NOT NULL, policy_version TEXT NOT NULL
);
CREATE TABLE snapshot (
  snapshot_hash TEXT PRIMARY KEY NOT NULL,
  governance_sha TEXT NOT NULL REFERENCES governance_document(governance_sha),
  protocols_sha TEXT NOT NULL REFERENCES artifact(sha256),
  routing_sha TEXT NOT NULL REFERENCES artifact(sha256),
  UNIQUE (governance_sha, protocols_sha, routing_sha)
);
CREATE TABLE agent (
  snapshot_hash TEXT NOT NULL REFERENCES snapshot(snapshot_hash),
  agent_id TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)), created_date TEXT,
  clearance TEXT NOT NULL CHECK (clearance IN ('public','internal','confidential','restricted')),
  max_depth INTEGER CHECK (max_depth >= 0), runtime TEXT, endpoint TEXT,
  PRIMARY KEY (snapshot_hash, agent_id)
);
CREATE TABLE capability (
  snapshot_hash TEXT NOT NULL REFERENCES snapshot(snapshot_hash),
  capability_id TEXT NOT NULL, PRIMARY KEY (snapshot_hash, capability_id)
);
CREATE TABLE agent_capability (
  snapshot_hash TEXT NOT NULL, agent_id TEXT NOT NULL, capability_id TEXT NOT NULL,
  PRIMARY KEY (snapshot_hash, agent_id, capability_id),
  FOREIGN KEY (snapshot_hash, agent_id) REFERENCES agent(snapshot_hash, agent_id),
  FOREIGN KEY (snapshot_hash, capability_id) REFERENCES capability(snapshot_hash, capability_id)
);
CREATE TABLE relationship (
  snapshot_hash TEXT NOT NULL REFERENCES snapshot(snapshot_hash),
  source_id TEXT NOT NULL, target_id TEXT NOT NULL, relationship_type TEXT NOT NULL,
  max_depth INTEGER CHECK (max_depth >= 0),
  requires_approval INTEGER NOT NULL CHECK (requires_approval IN (0, 1)),
  PRIMARY KEY (snapshot_hash, source_id, target_id, relationship_type),
  FOREIGN KEY (snapshot_hash, source_id) REFERENCES agent(snapshot_hash, agent_id),
  FOREIGN KEY (snapshot_hash, target_id) REFERENCES agent(snapshot_hash, agent_id)
);
CREATE TABLE relationship_param (
  snapshot_hash TEXT NOT NULL, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK (ordinal >= 0), value TEXT NOT NULL,
  PRIMARY KEY (snapshot_hash, source_id, target_id, relationship_type, ordinal),
  FOREIGN KEY (snapshot_hash, source_id, target_id, relationship_type)
    REFERENCES relationship(snapshot_hash, source_id, target_id, relationship_type)
);
```

```sql
CREATE TABLE decision_code (
  reason_code TEXT NOT NULL PRIMARY KEY,
  allowed INTEGER NOT NULL CHECK (allowed IN (0,1))
);
CREATE TABLE decision (
  decision_id TEXT NOT NULL PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES request(request_id),
  reason_code TEXT NOT NULL REFERENCES decision_code(reason_code),
  reason TEXT, policy_version TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE decision_snapshot (
  decision_id TEXT NOT NULL PRIMARY KEY REFERENCES decision(decision_id),
  snapshot_hash TEXT NOT NULL REFERENCES snapshot(snapshot_hash)
);
CREATE TABLE decision_rule (
  decision_id TEXT NOT NULL REFERENCES decision(decision_id),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0), rule_id TEXT NOT NULL,
  PRIMARY KEY (decision_id, ordinal)
);
CREATE TABLE reservation (
  request_id TEXT NOT NULL PRIMARY KEY REFERENCES request(request_id),
  calls INTEGER NOT NULL CHECK (calls >= 0), seconds REAL NOT NULL CHECK (seconds >= 0),
  released INTEGER NOT NULL CHECK (released IN (0,1)), created_at TEXT NOT NULL
);
CREATE TABLE replay (
  message_id TEXT NOT NULL PRIMARY KEY,
  envelope_hash TEXT NOT NULL UNIQUE REFERENCES envelope_identity(envelope_hash),
  artifact_ref TEXT, created_at TEXT NOT NULL
);
CREATE TABLE cancellation (run_id TEXT NOT NULL PRIMARY KEY REFERENCES run(run_id), at TEXT NOT NULL);
CREATE TABLE lease (
  workspace_key TEXT NOT NULL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES run(run_id), acquired_at TEXT NOT NULL
);
CREATE TABLE approval (
  approval_id TEXT NOT NULL PRIMARY KEY, run_id TEXT NOT NULL REFERENCES run(run_id),
  requester TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL,
  artifact_hash TEXT NOT NULL, risk TEXT NOT NULL, expires_at TEXT NOT NULL,
  approver TEXT, decision TEXT, decided_at TEXT
);
CREATE TABLE approval_rule (
  approval_id TEXT NOT NULL REFERENCES approval(approval_id),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0), rule_id TEXT NOT NULL,
  PRIMARY KEY (approval_id, ordinal)
);
CREATE TABLE import_source (
  source_id TEXT NOT NULL PRIMARY KEY, kind TEXT NOT NULL,
  source_sha TEXT NOT NULL REFERENCES artifact(sha256)
);
CREATE TABLE import_issue (
  source_id TEXT NOT NULL REFERENCES import_source(source_id),
  record_no INTEGER NOT NULL CHECK (record_no >= 0), code TEXT NOT NULL, detail TEXT,
  PRIMARY KEY (source_id, record_no, code)
);
```

```sql
CREATE TABLE run (run_id TEXT PRIMARY KEY NOT NULL, created_at TEXT, outcome TEXT);
CREATE TABLE run_budget (
  run_id TEXT PRIMARY KEY NOT NULL REFERENCES run(run_id),
  max_calls INTEGER CHECK (max_calls IS NULL OR max_calls >= 0),
  max_seconds REAL CHECK (max_seconds IS NULL OR max_seconds >= 0)
);
CREATE TABLE family (
  family_id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES run(run_id), label TEXT
);
CREATE TABLE envelope_identity (envelope_hash TEXT PRIMARY KEY NOT NULL);
CREATE TABLE envelope (
  envelope_hash TEXT PRIMARY KEY NOT NULL REFERENCES envelope_identity(envelope_hash),
  message_id TEXT NOT NULL, task_id TEXT NOT NULL, parent_task_id TEXT,
  correlation_id TEXT NOT NULL, sender TEXT NOT NULL, recipient TEXT NOT NULL, intent TEXT NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('request','response','error','cancellation','approval')),
  protocol TEXT NOT NULL, schema_name TEXT NOT NULL,
  classification TEXT NOT NULL CHECK (classification IN ('public','internal','confidential','restricted')),
  created_at TEXT NOT NULL, expires_at TEXT, deadline TEXT, reply_to TEXT,
  payload_sha TEXT REFERENCES artifact(sha256)
);
CREATE TABLE envelope_artifact (
  envelope_hash TEXT NOT NULL REFERENCES envelope(envelope_hash),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0), sha256 TEXT NOT NULL REFERENCES artifact(sha256),
  kind TEXT NOT NULL, PRIMARY KEY (envelope_hash, ordinal)
);
CREATE TABLE envelope_field (
  envelope_hash TEXT NOT NULL REFERENCES envelope(envelope_hash),
  section TEXT NOT NULL CHECK (section IN ('budget','provenance','security')),
  pointer TEXT NOT NULL, type TEXT NOT NULL CHECK (type IN ('string','number','boolean','null')),
  value TEXT, PRIMARY KEY (envelope_hash, section, pointer)
);
CREATE TABLE request (
  request_id TEXT PRIMARY KEY NOT NULL, family_id TEXT NOT NULL REFERENCES family(family_id),
  envelope_hash TEXT REFERENCES envelope_identity(envelope_hash)
);
CREATE TABLE node (
  node_id TEXT PRIMARY KEY NOT NULL REFERENCES request(request_id), route_id TEXT REFERENCES route(route_id),
  tier TEXT CHECK (tier IN ('cheap','mid','frontier')), task TEXT, created_at TEXT NOT NULL
);
CREATE TABLE node_event (
  event_id INTEGER PRIMARY KEY NOT NULL, node_id TEXT NOT NULL REFERENCES node(node_id),
  event_seq INTEGER NOT NULL CHECK (event_seq >= 0), status TEXT NOT NULL, occurred_at TEXT NOT NULL,
  UNIQUE (node_id, event_seq)
);
CREATE TABLE usage (
  event_id INTEGER PRIMARY KEY NOT NULL REFERENCES node_event(event_id),
  seconds REAL CHECK (seconds >= 0), subscription_calls INTEGER CHECK (subscription_calls >= 0),
  input_tokens INTEGER CHECK (input_tokens >= 0), output_tokens INTEGER CHECK (output_tokens >= 0),
  reasoning_tokens INTEGER CHECK (reasoning_tokens >= 0), cost_micro_usd INTEGER CHECK (cost_micro_usd >= 0)
);
CREATE TABLE lineage (
  child_id TEXT PRIMARY KEY NOT NULL REFERENCES node(node_id),
  parent_id TEXT NOT NULL REFERENCES node(node_id), CHECK (child_id <> parent_id)
);
CREATE TABLE graph_edge (
  source_id TEXT NOT NULL REFERENCES node(node_id), target_id TEXT NOT NULL REFERENCES node(node_id),
  edge_type TEXT NOT NULL CHECK (edge_type IN ('reviews','corrects','probes','depends-on')),
  PRIMARY KEY (source_id, target_id, edge_type), CHECK (source_id <> target_id)
);
CREATE TABLE legacy_parent (
  child_id TEXT PRIMARY KEY NOT NULL REFERENCES node(node_id), parent_id TEXT REFERENCES node(node_id),
  edge_type TEXT CHECK (edge_type IN ('reviews','corrects','probes','depends-on'))
);
CREATE TABLE edge_artifact (
  source_id TEXT NOT NULL, target_id TEXT NOT NULL, edge_type TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0), sha256 TEXT NOT NULL REFERENCES artifact(sha256), role TEXT NOT NULL,
  PRIMARY KEY (source_id, target_id, edge_type, ordinal),
  FOREIGN KEY (source_id, target_id, edge_type) REFERENCES graph_edge(source_id, target_id, edge_type)
);
CREATE TABLE frontier_gate (
  node_id TEXT PRIMARY KEY NOT NULL REFERENCES node(node_id), reason TEXT NOT NULL CHECK (trim(reason) <> '')
);
```

```sql
CREATE TABLE decision_identity (
  decision_id TEXT PRIMARY KEY NOT NULL REFERENCES decision(decision_id),
  authenticated_sender_id TEXT NOT NULL, recipient_id TEXT NOT NULL
);
CREATE TABLE node_artifact (
  node_id TEXT NOT NULL REFERENCES node(node_id),
  sha256 TEXT NOT NULL REFERENCES artifact(sha256), role TEXT NOT NULL,
  PRIMARY KEY (node_id,sha256,role)
);
CREATE VIEW node_state AS
SELECT n.node_id,
  (SELECT e.event_seq FROM node_event e WHERE e.node_id=n.node_id ORDER BY e.event_seq DESC LIMIT 1) AS event_seq,
  (SELECT e.status FROM node_event e WHERE e.node_id=n.node_id ORDER BY e.event_seq DESC LIMIT 1) AS status,
  (SELECT e.occurred_at FROM node_event e WHERE e.node_id=n.node_id ORDER BY e.event_seq DESC LIMIT 1) AS occurred_at
FROM node n;
CREATE VIEW node_usage AS
SELECT n.node_id,
  (SELECT u.seconds FROM node_event e JOIN usage u ON u.event_id=e.event_id
   WHERE e.node_id=n.node_id AND u.seconds IS NOT NULL ORDER BY e.event_seq DESC LIMIT 1) AS seconds,
  (SELECT u.subscription_calls FROM node_event e JOIN usage u ON u.event_id=e.event_id
   WHERE e.node_id=n.node_id AND u.subscription_calls IS NOT NULL ORDER BY e.event_seq DESC LIMIT 1) AS subscription_calls,
  (SELECT u.input_tokens FROM node_event e JOIN usage u ON u.event_id=e.event_id
   WHERE e.node_id=n.node_id AND u.input_tokens IS NOT NULL ORDER BY e.event_seq DESC LIMIT 1) AS input_tokens,
  (SELECT u.output_tokens FROM node_event e JOIN usage u ON u.event_id=e.event_id
   WHERE e.node_id=n.node_id AND u.output_tokens IS NOT NULL ORDER BY e.event_seq DESC LIMIT 1) AS output_tokens,
  (SELECT u.reasoning_tokens FROM node_event e JOIN usage u ON u.event_id=e.event_id
   WHERE e.node_id=n.node_id AND u.reasoning_tokens IS NOT NULL ORDER BY e.event_seq DESC LIMIT 1) AS reasoning_tokens,
  (SELECT u.cost_micro_usd FROM node_event e JOIN usage u ON u.event_id=e.event_id
   WHERE e.node_id=n.node_id AND u.cost_micro_usd IS NOT NULL ORDER BY e.event_seq DESC LIMIT 1) AS cost_micro_usd
FROM node n;
CREATE INDEX lineage_parent_idx ON lineage(parent_id);
CREATE INDEX legacy_parent_idx ON legacy_parent(parent_id);
CREATE INDEX graph_target_idx ON graph_edge(target_id,edge_type);
CREATE INDEX family_run_idx ON family(run_id);
CREATE INDEX request_family_idx ON request(family_id);
CREATE INDEX decision_request_idx ON decision(request_id);
```

Graph SQL. Named parameters; each block one sqlite3.execute. q1 = true spawn; replace both lineage references with legacy_parent for 002 parent-depth parity. Missing lineage evidence means unknown spawn depth, not proof of root: run q1 only on families with complete authenticated lineage. q1 reports cycles/disconnected cycles/foreign-family parents; invalid depth NULL. q2 = legacy subtree parity. q5 = general graph reach, diamond-safe. Known subtotals require missing-count disclosure; zero subtotal with missing>0 never means zero true usage. No-root node_count=0. Root included once; summed seconds = work, not parallel elapsed. q3 = vendor lint; unknown blocks strict independence. q4 = reason-presence lint only; nonempty reason never grants dispatch.

```sql
-- q1 ancestry_depth
WITH RECURSIVE
fam AS (
  SELECT n.node_id FROM request r JOIN node n ON n.node_id=r.request_id
  WHERE r.family_id=:family_id
),
walk(seed_id,node_id,depth,path,cycle) AS (
  SELECT node_id,node_id,0,'/'||hex(CAST(node_id AS BLOB))||'/',0 FROM fam
  UNION ALL
  SELECT w.seed_id,l.parent_id,w.depth+1,w.path||hex(CAST(l.parent_id AS BLOB))||'/',
    CASE WHEN instr(w.path,'/'||hex(CAST(l.parent_id AS BLOB))||'/')>0 THEN 1 ELSE 0 END
  FROM walk w JOIN lineage l ON l.child_id=w.node_id JOIN fam p ON p.node_id=l.parent_id
  WHERE w.cycle=0
),
maxdepth AS (SELECT seed_id AS node_id,MAX(depth) AS depth FROM walk GROUP BY seed_id),
cycles AS (SELECT seed_id AS node_id,MAX(cycle) AS has_cycle FROM walk GROUP BY seed_id),
dangling AS (
  SELECT DISTINCT w.seed_id AS node_id FROM walk w JOIN lineage l ON l.child_id=w.node_id
  LEFT JOIN fam p ON p.node_id=l.parent_id WHERE l.parent_id IS NOT NULL AND p.node_id IS NULL
)
SELECT f.node_id,
  CASE WHEN COALESCE(c.has_cycle,0)=1 OR d.node_id IS NOT NULL THEN NULL ELSE COALESCE(md.depth,0) END AS depth,
  CASE WHEN COALESCE(c.has_cycle,0)=1 OR d.node_id IS NOT NULL THEN NULL
       WHEN COALESCE(md.depth,0)>1 THEN 1 ELSE 0 END AS depth_gt1,
  COALESCE(c.has_cycle,0) AS has_cycle,
  CASE WHEN d.node_id IS NOT NULL THEN 1 ELSE 0 END AS has_dangling_parent,
  CASE WHEN COALESCE(c.has_cycle,0)=1 THEN 'cycle'
       WHEN d.node_id IS NOT NULL THEN 'dangling_parent' ELSE 'ok' END AS status
FROM fam f LEFT JOIN maxdepth md ON md.node_id=f.node_id
LEFT JOIN cycles c ON c.node_id=f.node_id LEFT JOIN dangling d ON d.node_id=f.node_id
ORDER BY f.node_id;
```

```sql
-- q2 subtree_metrics
WITH RECURSIVE root AS (
  SELECT n.node_id FROM node n JOIN request r ON r.request_id=n.node_id
  WHERE n.node_id=:root_id AND r.family_id=:family_id
), reach(node_id) AS (
  SELECT node_id FROM root
  UNION
  SELECT lp.child_id FROM reach r JOIN legacy_parent lp ON lp.parent_id=r.node_id
  JOIN request rq ON rq.request_id=lp.child_id WHERE rq.family_id=:family_id
)
SELECT COUNT(*) AS node_count,
  COALESCE(SUM(u.seconds),0) AS seconds_sum,COUNT(*)-COUNT(u.seconds) AS seconds_missing,
  COALESCE(SUM(u.subscription_calls),0) AS subscription_calls_sum,
  COUNT(*)-COUNT(u.subscription_calls) AS subscription_calls_missing,
  COALESCE(SUM(u.input_tokens),0) AS input_tokens_sum,COUNT(*)-COUNT(u.input_tokens) AS input_tokens_missing,
  COALESCE(SUM(u.output_tokens),0) AS output_tokens_sum,COUNT(*)-COUNT(u.output_tokens) AS output_tokens_missing,
  COALESCE(SUM(u.reasoning_tokens),0) AS reasoning_tokens_sum,COUNT(*)-COUNT(u.reasoning_tokens) AS reasoning_tokens_missing,
  COALESCE(SUM(u.cost_micro_usd),0) AS cost_micro_usd_sum,COUNT(*)-COUNT(u.cost_micro_usd) AS cost_micro_usd_missing
FROM reach d LEFT JOIN node_usage u USING(node_id);
```

```sql
-- q3 reviewer_other_vendor_lint
SELECT ge.source_id,ge.target_id,ge.edge_type,rs.family_id,
  sm.vendor_id AS source_vendor_id,tm.vendor_id AS target_vendor_id,
  CASE WHEN sm.vendor_id IS NULL OR tm.vendor_id IS NULL THEN 'unknown_vendor' ELSE 'same_vendor_review' END AS lint_status
FROM graph_edge ge JOIN node ns ON ns.node_id=ge.source_id
JOIN request rs ON rs.request_id=ns.node_id AND rs.family_id=:family_id
JOIN node nt ON nt.node_id=ge.target_id
JOIN request rt ON rt.request_id=nt.node_id AND rt.family_id=:family_id
LEFT JOIN route sr ON sr.route_id=ns.route_id LEFT JOIN model sm ON sm.model_id=sr.model_id
LEFT JOIN route tr ON tr.route_id=nt.route_id LEFT JOIN model tm ON tm.model_id=tr.model_id
WHERE ge.edge_type='reviews' AND (sm.vendor_id IS NULL OR tm.vendor_id IS NULL OR sm.vendor_id=tm.vendor_id)
ORDER BY ge.source_id,ge.target_id;
```

```sql
-- q4 frontier_without_gate
SELECT n.node_id,n.tier,fg.reason AS gate_reason,
  CASE WHEN fg.node_id IS NULL THEN 'missing_gate'
       WHEN trim(COALESCE(fg.reason,''))='' THEN 'blank_gate_reason' ELSE 'gated' END AS gate_status
FROM node n JOIN request r ON r.request_id=n.node_id
LEFT JOIN frontier_gate fg ON fg.node_id=n.node_id
WHERE r.family_id=:family_id AND n.tier='frontier'
  AND (fg.node_id IS NULL OR trim(COALESCE(fg.reason,''))='')
ORDER BY n.node_id;
```

```sql
-- q5 graph_subtree_calls
WITH RECURSIVE reach(node_id) AS (
  SELECT n.node_id FROM node n JOIN request rq ON rq.request_id=n.node_id
  WHERE n.node_id=:root_id AND rq.family_id=:family_id
  UNION
  SELECT ge.source_id FROM graph_edge ge JOIN reach rr ON ge.target_id=rr.node_id
  JOIN request rq ON rq.request_id=ge.source_id
  WHERE rq.family_id=:family_id AND ge.edge_type IN ('reviews','corrects','depends-on','probes')
)
SELECT COUNT(*) AS node_count,COALESCE(SUM(nu.subscription_calls),0) AS subscription_calls,
  COALESCE(SUM(CASE WHEN nu.subscription_calls IS NULL THEN 1 ELSE 0 END),0) AS missing_count
FROM reach r LEFT JOIN node_usage nu ON nu.node_id=r.node_id;
```

Migration plan. `tools/migrate_to_3nf.py WORKSPACE [--db PATH] [--dry-run]` is canonical. Hash `ledger.jsonl` and `control.sqlite`; combine hashes; create artifact+import_source. Existing source_id means whole import skip: zero new facts. Missing explicit workspace with `--db` records `workspace_not_found`; missing workspace without `--db` exits 2. Ledger merge is last-timestamp-per-node before import. Per node: run; synthetic family per run; request_id=node_id; provider/model/route; node; terminal node_event+usage; lineage for known parent; graph_edge for typed parent; legacy_parent always, including parentless probe type. Historic vendor, envelope, artifact and original family boundaries stay unknown; do not invent. Control migration maps decisions+codes, reservations, replay keys, cancellations, run leases and approvals. Absent legacy tables skip. One transaction per ledger/control phase; phase failure rolls back and records import_issue. Dry-run reports only. Cutover: backup source files; migrate staging DB; run schema load, q1–q5, Tim/Dom Mermaid+rollup+lint parity and idempotence; stop writers; migrate final hashes; set `WORKERBEES_STORE=sqlite`; retain sources and proof; rollback by restoring `WORKERBEES_STORE=jsonl`. `both` is bounded parity observation, not permanent authority.

CEO open questions. Q1: add snapshot-scoped node→agent attribution so per-agent usage/cost is queryable, or keep attribution outside this schema? Q2: require authenticated lineage for every new family before depth enforcement, or allow explicit incomplete-lineage state? Q3: retain raw envelope artifacts in this DB under a defined access/retention policy, or store only hashes and allowlisted scalar fields? Q4: make ledger/control phase import atomic together, or retain independent rollback plus import_issue evidence?

Per-agent cost. Astra plan/judge: subscription, token count unavailable, $0 incremental. Gemini Flash Lite drafts ×4: 13.2k input/5.5k output aggregate, $0. OpenRouter Nemotron 3 Ultra drafts ×2: 6.5k input/8.6k output aggregate, $0. GPT-5.4-mini DDL: not reached in original scope run; 0 output, $0. Luna FD review: pending T6b. Total incremental spend: $0. These are build-family costs, not runtime node costs; runtime per-agent cost is not derivable until Q1 is resolved.

STATUS 2026-09-06. T6 complete: migration, four CEO questions and per-agent cost added; stale incomplete trailer removed. Canonical shape remains 42 tables+2 views; q1–q5 load/execute. T6b Luna FD verdict pending.

REVIEW OF RECORD (T6b, 2026-09-06). gpt-5.6-luna, codex read-only, run by fable outside sandbox (nested codex EPERM from sol). Checked 42 tables: FDs vs DDL, derived cols, BCNF-only splits, q1–q5 names, store.py writes. CLEAN 42/42. VERDICT PASS: "DDL, q1–q5, and store.py match stated FDs. No derived columns, denormalized writes, or BCNF-only splits found." Transcript .scratch/luna_fd.out (not committed).
