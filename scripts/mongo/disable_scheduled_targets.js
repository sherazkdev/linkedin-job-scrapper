// Operator: mongosh — only against pilot/test DB (e.g. global_jobs_pilot), not production global_jobs.
db.collection_targets.updateMany({ source: "fixture" }, { $set: { enabled: false } });
db.collection_targets.updateMany({ source: "linkedin" }, { $set: { enabled: false } });
printjson({
  linkedin_enabled: db.collection_targets.countDocuments({ source: "linkedin", enabled: true }),
  fixture_enabled: db.collection_targets.countDocuments({ source: "fixture", enabled: true }),
});