---
name: fullstack
description: Fullstack application development with frontend and backend subsystems
version: 1.0.0
triggers:
  - fullstack
  - full stack
  - frontend backend
  - react api
  - next.js api
  - vue backend
  - monorepo
  - full-stack
tags:
  - fullstack
  - frontend
  - backend
  - monorepo
  - multi-subsystem
composites:
  - web-app
  - backend-api
---

# Fullstack Application Development

## Summary

Fullstack applications combine frontend and backend subsystems. Key challenges:

1. **Cross-subsystem consistency** - Types, contracts, validation shared
2. **Development workflow** - Running both systems together
3. **Deployment coordination** - Versioning, rollbacks, feature flags
4. **Shared context** - Agent understands relationships between subsystems

**Project structures:**

```
# Monorepo (recommended)
fullstack-app/
├── packages/
│   ├── frontend/          # React/Next.js/Vue
│   │   ├── src/
│   │   └── package.json
│   ├── backend/           # FastAPI/Express/Go
│   │   ├── src/
│   │   └── pyproject.toml
│   └── shared/            # Shared types, utils
│       ├── types/
│       └── package.json
├── package.json           # Workspace root
└── turbo.json             # Build orchestration

# Polyrepo
frontend-app/              # Separate repo
backend-api/               # Separate repo
shared-contracts/          # Shared types repo
```

**Key principles:**
- Single source of truth for types/contracts
- Parallel development with clear boundaries
- Shared validation logic
- Coordinated testing and deployment

## Details

### Workspace Configuration

**Monorepo with pnpm/npm workspaces:**
```json
// package.json (root)
{
  "name": "fullstack-app",
  "private": true,
  "workspaces": [
    "packages/*"
  ],
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "test": "turbo run test",
    "lint": "turbo run lint"
  },
  "devDependencies": {
    "turbo": "^2.0.0"
  }
}
```

**Turborepo configuration:**
```json
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "test": {
      "dependsOn": ["build"]
    }
  }
}
```

### Shared Types/Contracts

**TypeScript shared types:**
```typescript
// packages/shared/types/user.ts
export interface User {
  id: string;
  email: string;
  name: string;
  createdAt: Date;
}

export interface CreateUserRequest {
  email: string;
  name: string;
  password: string;
}

export interface CreateUserResponse {
  user: User;
  token: string;
}

// Validation schemas (used by both frontend and backend)
export const createUserSchema = z.object({
  email: z.string().email(),
  name: z.string().min(2).max(100),
  password: z.string().min(8),
});
```

**Python backend using shared types:**
```python
# packages/backend/src/models/user.py
from pydantic import BaseModel, EmailStr
from datetime import datetime

class User(BaseModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime

class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str

    class Config:
        # Match TypeScript validation
        str_min_length = 2
```

### API Contract Synchronization

**OpenAPI/Swagger as contract:**
```yaml
# packages/shared/openapi.yaml
openapi: 3.0.0
info:
  title: Fullstack App API
  version: 1.0.0
paths:
  /api/users:
    post:
      operationId: createUser
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateUserRequest'
      responses:
        '201':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CreateUserResponse'
```

**Generate clients from OpenAPI:**
```bash
# Generate TypeScript client for frontend
npx openapi-typescript-codegen \
  --input packages/shared/openapi.yaml \
  --output packages/frontend/src/api

# Generate Python client (for testing)
openapi-python-client generate \
  --path packages/shared/openapi.yaml \
  --output-path packages/backend/tests/client
```

### Cross-Subsystem Development

**Running both systems:**
```bash
# Development (concurrent)
pnpm dev  # Runs both frontend and backend via Turborepo

# Or manually
cd packages/backend && uvicorn main:app --reload &
cd packages/frontend && npm run dev &
```

**Environment configuration:**
```bash
# packages/backend/.env
FRONTEND_URL=http://localhost:3000
DATABASE_URL=postgresql://localhost/app
```

**IMPORTANT — Frontend API client:**
Do NOT hardcode `http://localhost:8000` as the API base URL in the frontend. This breaks in cloud environments (Codespaces, Gitpod, deployed apps) where the browser's `localhost` is the user's machine, not the server.

Instead, use Next.js rewrites to proxy API requests server-side:
```typescript
// next.config.ts — proxy /api/* to backend
const nextConfig: NextConfig = {
  async rewrites() {
    return [{
      source: '/api/:path*',
      destination: process.env.BACKEND_URL
        ? `${process.env.BACKEND_URL}/api/:path*`
        : 'http://localhost:8000/api/:path*',
    }];
  },
};
```
```typescript
// frontend/src/lib/api.ts — use empty baseURL (relative paths)
const api = axios.create({
  baseURL: '',  // requests go to /api/* → Next.js rewrites → backend
  headers: { 'Content-Type': 'application/json' },
});
```

### Cross-Subsystem Testing

**End-to-end tests:**
```typescript
// e2e/user-flow.spec.ts
import { test, expect } from '@playwright/test';

test('user registration flow', async ({ page }) => {
  // Frontend interaction
  await page.goto('/register');
  await page.fill('[name=email]', 'test@example.com');
  await page.fill('[name=name]', 'Test User');
  await page.fill('[name=password]', 'securepass123');
  await page.click('button[type=submit]');

  // Verify backend processed correctly
  await expect(page).toHaveURL('/dashboard');
  await expect(page.locator('.user-name')).toContainText('Test User');
});
```

**Contract testing:**
```typescript
// packages/frontend/tests/api-contract.test.ts
import { createUserSchema } from '@shared/types';

test('frontend sends valid create user request', () => {
  const request = {
    email: 'test@example.com',
    name: 'Test',
    password: 'password123',
  };

  expect(() => createUserSchema.parse(request)).not.toThrow();
});
```

## Advanced

### Service Contract Modeling

```python
# packages/shared/contracts.py
from dataclasses import dataclass
from typing import Protocol, TypeVar, Generic

T = TypeVar('T')
R = TypeVar('R')

@dataclass
class ServiceContract(Generic[T, R]):
    """Define contract between frontend and backend."""
    name: str
    request_type: type[T]
    response_type: type[R]
    endpoint: str
    method: str = "POST"

# Define contracts
CREATE_USER = ServiceContract(
    name="createUser",
    request_type=CreateUserRequest,
    response_type=CreateUserResponse,
    endpoint="/api/users",
    method="POST",
)

GET_USER = ServiceContract(
    name="getUser",
    request_type=str,  # user_id
    response_type=User,
    endpoint="/api/users/{id}",
    method="GET",
)
```

### Workspace-Aware Context

```python
from reliable_ai.workspace import WorkspaceManager, Subsystem

# Initialize workspace
workspace = WorkspaceManager("./fullstack-app")

# Define subsystems
workspace.add_subsystem(Subsystem(
    name="frontend",
    path="packages/frontend",
    type="nextjs",
    port=3000,
))

workspace.add_subsystem(Subsystem(
    name="backend",
    path="packages/backend",
    type="fastapi",
    port=8000,
))

workspace.add_subsystem(Subsystem(
    name="shared",
    path="packages/shared",
    type="library",
))

# Get cross-subsystem context
context = workspace.get_context()
# Returns: relationships, shared types, API contracts
```

### Coordinated Deployment

```yaml
# .github/workflows/deploy.yml
name: Deploy Fullstack

on:
  push:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      frontend: $
      backend: $
    steps:
      - uses: dorny/paths-filter@v2
        id: changes
        with:
          filters: |
            frontend:
              - 'packages/frontend/**'
              - 'packages/shared/**'
            backend:
              - 'packages/backend/**'
              - 'packages/shared/**'

  deploy-backend:
    needs: detect-changes
    if: needs.detect-changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy backend
        run: |
          # Deploy to Cloud Run/ECS/etc

  deploy-frontend:
    needs: [detect-changes, deploy-backend]
    if: needs.detect-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy frontend
        run: |
          # Deploy to Vercel/Netlify/etc
```

### Feature Flags Across Subsystems

```typescript
// packages/shared/features.ts
export const FEATURES = {
  NEW_CHECKOUT: 'new-checkout',
  DARK_MODE: 'dark-mode',
  BETA_API: 'beta-api',
} as const;

// Frontend usage
import { useFeatureFlag } from '@/hooks/features';
const showNewCheckout = useFeatureFlag(FEATURES.NEW_CHECKOUT);

// Backend usage
from shared.features import FEATURES
if feature_enabled(FEATURES.BETA_API, user):
    return beta_response()
```

## Agent Workflow

When working on fullstack apps, the agent should:

1. **Understand the workspace structure**
   - Identify subsystems and their relationships
   - Find shared types/contracts
   - Understand build dependencies

2. **Make coordinated changes**
   - Update shared types first
   - Update backend to implement
   - Update frontend to consume
   - Add tests at each layer

3. **Validate cross-subsystem**
   - Run contract tests
   - Verify type compatibility
   - Check API versioning

```python
from reliable_ai.workspace import WorkspaceManager

# Agent workflow for adding new feature
workspace = WorkspaceManager(".")

# 1. Plan changes across subsystems
changes = workspace.plan_feature("Add user preferences")
# Returns: [
#   ("shared", "Add PreferencesType"),
#   ("backend", "Add /api/preferences endpoint"),
#   ("frontend", "Add preferences page"),
# ]

# 2. Execute in order with validation
for subsystem, change in changes:
    workspace.switch_context(subsystem)
    # Make changes...
    workspace.validate_contracts()
```

## Resources

- [Turborepo Docs](https://turbo.build/repo/docs)
- [pnpm Workspaces](https://pnpm.io/workspaces)
- [OpenAPI Generator](https://openapi-generator.tech/)
- [Playwright E2E Testing](https://playwright.dev/)
