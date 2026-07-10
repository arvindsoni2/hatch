# Cloud Providers

Current cloud-provider documentation covers the providers exposed through the current setup flow.

## Current Providers

| Provider | Secret name | Notes |
|---|---|---|
| Google Gemini | `GOOGLE_API_KEY` | Stored canonically as `google_genai` |
| OpenRouter | `OPENROUTER_API_KEY` | Supports provider test flow in setup |
| OpenAI | `OPENAI_API_KEY` | Host-managed secret |
| Anthropic | `ANTHROPIC_API_KEY` | Host-managed secret |

## Configuration Path

Use the UI to choose the provider and non-secret metadata, then write the secret from the host:

```bash
hatch secrets set openrouter
```

## Model Selection

Provider metadata such as model slug is stored in non-secret setup intent and effective runtime config.

## Test Connection

The setup API can test OpenRouter directly when a secret exists. Other providers are currently tracked as configured/not-tested rather than fully exercised from the browser.

## Failure States

- missing secret
- invalid secret
- provider unavailable
- model not found
- rate limited

## Privacy

Cloud providers receive data only when configured and used for an AI-backed operation.

## Removal

```bash
hatch secrets unset openrouter --yes
```
