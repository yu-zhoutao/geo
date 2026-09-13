# Thesis Scorecards

## Scored Dimensions

Each judged run receives only these 1-5 LLM judge scores:

- Method selection
- Data readiness
- CRS and units
- Parameterization
- Execution correctness
- Uncertainty and sensitivity
- Claim validity
- Map and report quality
- Repair or stop judgment
- Overall task success

## Runtime Facts

These fields describe how the task ran, but they are not scoring dimensions:

- session status
- terminal reason
- timeout state
- duration
- continuation count
- error count
- error messages
- judge attempt count
- judge retry errors

Structured app artifacts such as `study_design.json`, `claim_trace.json`, and `evidence-records.json`
support reproducibility and dashboard inspection. They may help the judge understand the run when they
contain substantive analytical evidence, but missing framework-specific structures are not pass/fail gates.
