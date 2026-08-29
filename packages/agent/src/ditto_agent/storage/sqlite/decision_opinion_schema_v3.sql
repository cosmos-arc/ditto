-- Add exact newest-first lookup for immutable Daily Decision V3 artifacts.
CREATE INDEX shadow_decision_opinions_artifact_generated
ON shadow_decision_opinions(v3_artifact_id, generated_at_us DESC, opinion_id DESC);

PRAGMA application_id = 1146373976;
PRAGMA user_version = 3;
