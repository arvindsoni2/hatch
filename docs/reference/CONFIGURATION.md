# Configuration

Current Hatch configuration is split across:

- `.env` for local/dev container environment values
- `data/profile.yaml` for saved profile and product preferences
- `${HATCH_HOME}/config/ai_setup_intent.json` for non-secret setup intent
- `${HATCH_HOME}/config/ai_runtime.json` for effective runtime configuration
- `${HATCH_HOME}/config/backend_capabilities.json` for backend profile state
- `${HATCH_HOME}/config/secrets.env` for provider secrets in easy installs
