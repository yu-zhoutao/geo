# Baselines And Ablations

## Baselines
- B0 deterministic GIS reference pipeline
- B1 monolithic single agent
- B2 single agent plus skill packs
- B3 planner-worker two-agent baseline
- B4 full multi-agent without skeptical review
- B5 full system

## Ablations
- no skeptical review
- no explicit control states
- no skill packs
- monolithic prompt instead of specialist roles
- no evidence ledger or claim trace
- no CRS-safety skill
- post-hoc review only vs mid-run plus final review
- same reviewer model vs stronger reviewer model
