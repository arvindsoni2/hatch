---
title: Hatch Workflows
document_type: architecture
status: current
implementation_status: not-applicable
applies_to: main
last_verified: 2026-11-27
supersedes: []
superseded_by: []
---

# Workflows

## Onboarding

Onboarding collects the search profile, stores a local workspace profile, and records non-secret AI/setup intent. The app-lock password is handled separately through the protected setup flow.

## Discovery To Application

```mermaid
flowchart LR
    A[Scout discovers or imports role]
    B[Normalise and deduplicate]
    C[Scorer evaluates profile fit]
    D{Above shortlist threshold?}
    E[Ready for review]
    F[Parked]
    G[User reviews evidence]
    H[Generate CV pack]
    I[User reviews documents]
    J[User applies externally]
    K[Track application state]

    A --> B --> C --> D
    D -->|Yes| E --> G
    D -->|No| F
    G -->|Proceed| H --> I --> J --> K
    G -->|Not now| F
```

## Interview Preparation

```mermaid
flowchart LR
    A[Application reaches interview stage]
    B[Create preparation session]
    C[Gather role and company context]
    D[Generate likely questions]
    E[Reuse Question Bank answers]
    F[Prepare STAR guidance]
    G[User reviews and practices]
    H[Export or continue preparation]

    A --> B --> C --> D
    D --> E
    D --> F
    E --> G
    F --> G --> H
```

## Coach Practice Session

```mermaid
flowchart LR
    A[Choose role, interview type and difficulty]
    B[Generate questions from role and CV evidence]
    C[User answers by typing or speaking]
    D[Transcribe and measure delivery]
    E[Evaluate answer against evidence]
    F{Follow-up needed?}
    G[Ask follow-up]
    H[Session report]

    A --> B --> C --> D --> E --> F
    F -->|Yes| G --> C
    F -->|No| H
```

Spoken answers use the conversational mode, which is off by default (`HATCH_COACH_CONVERSATIONAL_ENABLED`). With AI mode set to None, sessions still run with deterministic questions and evaluation.

## Interview Readiness Loop

```mermaid
flowchart LR
    P[Practice sessions] --> Pat[Patterns]
    Pat --> F[Focus areas]
    F --> Plan[Practice plan]
    Plan --> B[Interview brief]
    B --> R[Real interview]
    R --> D[Debrief]
    D --> P
```

Before a scheduled interview round the user gets a one-page brief built from their own evidence; after it, a short debrief feeds the next round. Patterns, focus areas and plans, the brief, the debrief and story coverage are each opt-in and off by default. Model output is a proposal: the user accepts or edits it, and every part renders deterministic content with AI mode set to None.

## Human-Control Boundary

```mermaid
flowchart TD
    Automated[Automated or assisted work]
    Review[Human review]
    External[External action]

    Automated --> Review
    Review -->|Approved by user| External
    Review -->|Rejected or revised| Automated
```

Hatch may discover, score, generate, and recommend. It does not autonomously submit applications or contact recruiters.

## Application Tracking

Applications move through current product states such as saved, discovered, preparing, ready to apply, applied, interview, and offered. Some closed outcomes are explicit end states rather than drag targets.

## Company Watchlist

The watchlist lives under Applications and supports saved companies plus manual scans. Discovered roles from watched companies feed back into the broader workflow rather than creating a separate top-level product area.

## AI Setup And Provider Selection

Setup captures non-secret intent in the app, while the host CLI writes provider secrets and effective runtime configuration.

## Reset And Restart

The repo includes a local data reset flow, a separate app-lock reset flow, and a non-destructive uninstall by default. These are documented in operations and storage docs rather than hidden in implementation notes.
