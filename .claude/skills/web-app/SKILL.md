---
name: web-app
description: Frontend web app conventions for this project
version: 1.0.0
triggers:
  - react
  - next.js
  - nextjs
  - frontend
  - dashboard
  - component
tags:
  - frontend
  - typescript
  - ui
---

# Frontend Conventions

## Project Structure

```
frontend/
├── src/
│   ├── app/           # Next.js App Router pages
│   ├── components/    # Reusable React components
│   ├── lib/           # API client, auth utils, helpers
│   └── __tests__/     # Jest component tests
├── tailwind.config.ts
├── jest.config.js
└── next.config.js
```

## Key Conventions

- **Next.js 14** with App Router and TypeScript
- **Tailwind CSS** for styling — verify `content` paths match actual file locations
- API calls via `frontend/src/lib/api.ts` — do NOT hardcode `localhost:8000`
- Use `'use client'` directive only for components needing state, effects, or event handlers
- Jest + React Testing Library for component tests
- Run `npm test && npm run build` before marking any feature complete
