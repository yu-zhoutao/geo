## Purpose
Define how the app selects between GLM and DeepSeek for the backend-managed OpenCode agent runtime while preserving GLM as the default provider.

## Requirements

### Requirement: Runtime provider is selected explicitly
The backend SHALL select the backend-managed OpenCode runtime provider from an explicit application setting and SHALL keep GLM as the default provider.

#### Scenario: GLM remains default
- **WHEN** the app starts without `GEO_AGENT_MODEL_PROVIDER`
- **THEN** the backend selects the GLM runtime provider
- **AND** existing GLM environment settings continue to control the runtime model and auth credential

#### Scenario: DeepSeek is selected explicitly
- **WHEN** the app starts with `GEO_AGENT_MODEL_PROVIDER=deepseek`
- **THEN** the backend selects the DeepSeek runtime provider
- **AND** it uses DeepSeek-specific environment settings for runtime model and auth credential

#### Scenario: Unknown provider is rejected
- **WHEN** `GEO_AGENT_MODEL_PROVIDER` is set to a value other than `glm` or `deepseek`
- **THEN** settings validation fails instead of silently falling back to another provider

### Requirement: DeepSeek runtime settings are environment managed
The backend SHALL expose DeepSeek runtime configuration through environment-managed settings and SHALL require a DeepSeek API key only when DeepSeek is selected as the runtime provider.

#### Scenario: DeepSeek model setting has evaluation default
- **WHEN** the app settings are constructed without `GEO_AGENT_DEEPSEEK_MODEL`
- **THEN** the DeepSeek model setting defaults to `deepseek-v4-pro`

#### Scenario: DeepSeek key is required only for DeepSeek runtime
- **WHEN** `GEO_AGENT_MODEL_PROVIDER=deepseek`
- **THEN** real agent runtime readiness requires `GEO_AGENT_DEEPSEEK_API_KEY`

#### Scenario: DeepSeek key does not opt in automatically
- **WHEN** `GEO_AGENT_DEEPSEEK_API_KEY` is present but `GEO_AGENT_MODEL_PROVIDER` is unset
- **THEN** the backend still selects the GLM runtime provider

### Requirement: Runtime status reports selected provider
The backend SHALL expose enough provider metadata for app health and evaluation logs to identify which runtime provider and model are selected.

#### Scenario: Health metadata identifies DeepSeek runtime
- **WHEN** the selected runtime provider is DeepSeek
- **THEN** backend health metadata identifies the runtime provider as `deepseek`
- **AND** reports the selected DeepSeek model without exposing the API key

#### Scenario: Health metadata identifies GLM runtime
- **WHEN** the selected runtime provider is GLM
- **THEN** backend health metadata identifies the runtime provider as `glm`
- **AND** reports the selected GLM model without exposing the API key

### Requirement: Runtime provider selection does not change evaluation judge provider
The backend SHALL keep LLM judge provider selection out of the runtime provider selector unless a later specification explicitly adds judge-provider selection.

#### Scenario: DeepSeek runtime leaves judge behavior unchanged
- **WHEN** an evaluation run uses `GEO_AGENT_MODEL_PROVIDER=deepseek`
- **THEN** the OpenCode agent runtime uses DeepSeek
- **AND** existing judge scoring continues to use its current judge provider path
