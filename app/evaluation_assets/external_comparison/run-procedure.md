# External Framework Comparison Run Procedure

This procedure records how to run GIS Copilot and GeoCogent for the thesis same-case, same-rubric comparison. It is an experiment asset, not app runtime configuration.

## Shared Case Setup

1. Use `app/evaluation_assets/external_comparison/thesis-giscopilot-geocogent-v1.yaml` as the scenario list.
2. For each scenario, copy the exact benchmark `user_prompt` into the external framework without hidden rewriting.
3. Make the scenario dataset files available from the same `dataset_root` and `dataset_pack` entries recorded in the benchmark fixture.
4. Run three attempts for every framework/scenario setup and record model provider, model name, temperature, start time, finish time, timeout state, and any errors.

## GIS Copilot

1. Install or open the GIS Copilot QGIS plugin or its published script environment.
2. Load the scenario dataset files into QGIS or the plugin's expected workspace.
3. Submit the unchanged scenario prompt.
4. Save the plugin transcript, QGIS processing logs, generated scripts, final answer, screenshots or exported layers, and operator notes.
5. Place the files into an evidence-pack directory following `evidence-pack-template.json` under a project-root `evaluation-runs/` archive directory, not under versioned evaluation assets.

## GeoCogent

1. Install or open the public GeoCogent demo/code assets or a faithful local reproduction of its staged code-generation flow.
2. Provide the unchanged scenario prompt and the same dataset paths.
3. Save generated code, execution logs, repair attempts, final answer, output artifacts, and operator notes.
4. Place the files into an evidence-pack directory following `evidence-pack-template.json` under a project-root `evaluation-runs/` archive directory, not under versioned evaluation assets.

## Import And Score

1. Validate and import one evidence pack:
   `python -m app.evaluation.external_frameworks <evidence-pack-or-dir> <campaign-output-root>`
2. Use a project-root `evaluation-runs/<external-comparison-run-id>/campaign` directory as `<campaign-output-root>` for real imported runs.
3. Score the imported campaign root with the core geospatial-quality LLM judge dimensions.
4. Use the generated `exports/run-scores.csv`, `exports/variant-scenario-scores.csv`, `exports/variant-dimension-scores.csv`, and `exports/campaign-summary.json` for thesis tables.
