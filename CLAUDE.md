# Learning Architecture — Claude Code Project Instructions

## What This Is
Claudia Canu Fautré's professional portfolio of educational design frameworks, case studies, and methods. This is a **learning design portfolio**, not a code repository.

## Palette Connection

This repo is governed by Palette methodology from `~/pretendhome/palette/`. All substantive changes should follow the Palette skill execution cadence.

### Before Making Changes

1. **Pull latest from both repos**:
   ```bash
   cd ~/learning-architecture && git pull origin main
   cd ~/pretendhome && git pull origin main
   ```

2. **Load the relevant Palette skill**:
   - For content/case studies: `~/pretendhome/palette/skills/education/`
   - For resume/CV updates: `~/pretendhome/palette/skills/talent/`
   - For Claudia's full profile: `~/pretendhome/palette/skills/talent/claudia-canu-fautre-profile.md`

3. **Check the publication policy** (`publication-policy.md`) before adding content:
   - No institution names (use "a 4-campus IB international school")
   - No student names or individual data
   - No colleague names
   - No proprietary school documents
   - Every artifact must have a maturity label: `observed`, `designed`, `proposed`, `piloted`, `validated`

4. **Use Palette's evidence bar**:
   - Claims must be traceable to evidence
   - Numbers must be real and defensible
   - Maturity labels must be honest — don't present `proposed` work as `validated`

### Commit Convention
```
<type>(<scope>): <description>

Types: feat, fix, docs, refactor
Scopes: case-study, method, resume, meta
```

### Push Protocol
```bash
cd ~/learning-architecture
git add <specific files>
git commit -m "<type>(<scope>): <description>"
git push origin main
```

## Repository Structure

```
learning-architecture/
├── case-studies/
│   ├── 01-structural-coherence/    # 6-layer diagnostic framework
│   ├── 02-ai-classroom/           # AI for continuity problem
│   └── 03-lingua-viva/            # K-5 curriculum integration
├── methods/
│   ├── assessment-philosophy.md    # Evidence-based assessment (validated)
│   └── teacher-ai-workflow.md      # Daily AI practice (validated)
├── resume-cv/
│   └── Claudia_CanuFautre_Resume.docx
├── publication-policy.md
├── README.md
└── CLAUDE.md                       # This file
```

## Key Rules

1. **Privacy first.** Never commit identifiable student data, institution names, or colleague names. See `publication-policy.md`.
2. **Honest maturity labels.** Every framework/method gets a label. Don't inflate.
3. **Palette source of truth.** Claudia's profile, job search data, and career strategy live in Palette (`~/pretendhome/palette/skills/talent/`). This repo is the public-facing portfolio — it should be consistent with but not duplicate the Palette files.
4. **Evidence-based claims only.** If you cite a number (93% improvement, 200+ students), it must be real and defensible.
5. **Glass-box.** Every design decision should be traceable. No black boxes.

## Do NOT
- Commit personally identifiable information about children
- Name the school (use generic description)
- Present proposed work as validated
- Duplicate Palette files here — reference them
- Push without checking publication policy
