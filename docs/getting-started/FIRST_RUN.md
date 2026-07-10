# First Run

After installation, open <http://localhost:3000>. Hatch will guide you through local workspace setup.

## First Session

1. Create the local app-lock password.
2. Complete onboarding for market, target roles, locations, compensation, eligibility, and skills.
3. Choose the Hatch experience and either defer AI, configure a cloud provider, or prepare local AI.
4. Upload or confirm the Master CV.
5. Save the profile.

## AI Choice

Hatch can start with AI configuration deferred. In that state, profile editing, manual application tracking, and settings remain available. AI-assisted scoring, tailoring, and coaching stay limited until a provider or local runtime is configured.

## Host Follow-Up Commands

Depending on your choices, the next host command may be:

```bash
hatch secrets set openrouter
hatch probe
hatch models install
hatch apply-ai-config
```

## Verify The Workspace

After onboarding:

- Today should open without redirecting back to onboarding.
- Pipeline and Applications should show empty states rather than errors.
- Settings should show your saved profile and AI setup state.

## If Setup Feels Incomplete

- Re-open [AI & Capabilities](../user-guide/SETTINGS.md)
- Check [Troubleshooting](TROUBLESHOOTING.md)
- Run `hatch status` and `hatch doctor`
