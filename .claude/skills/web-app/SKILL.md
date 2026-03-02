---
name: web-app
description: Frontend web application development with React, Next.js, Vue, and modern tooling
version: 1.0.0
triggers:
  - react
  - next.js
  - nextjs
  - vue
  - frontend
  - web app
  - dashboard
  - spa
  - single page
  - component
  - jsx
  - tsx
tags:
  - frontend
  - javascript
  - typescript
  - ui
  - components
---

# Web Application Development

## Summary

Modern web apps follow component-based architecture with:
- **Components** - Reusable UI building blocks
- **State management** - Local (useState) vs global (Redux/Zustand/Pinia)
- **Routing** - Client-side navigation (React Router, Next.js App Router, Vue Router)
- **Data fetching** - REST/GraphQL with caching (TanStack Query, SWR)
- **Styling** - CSS Modules, Tailwind, styled-components, or CSS-in-JS

**Project structure:**
```
src/
├── components/     # Reusable UI components
├── pages/          # Route components (or app/ for Next.js 13+)
├── hooks/          # Custom React hooks
├── lib/            # Utilities, API clients
├── stores/         # Global state
└── styles/         # Global styles, themes
```

**Key principles:**
1. Prefer composition over inheritance
2. Keep components small and focused
3. Lift state to lowest common ancestor
4. Use TypeScript for type safety
5. Implement error boundaries

## Details

### Component Patterns

**Functional components with hooks (React):**
```tsx
interface UserCardProps {
  user: User;
  onSelect?: (user: User) => void;
}

export function UserCard({ user, onSelect }: UserCardProps) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div
      className={styles.card}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={() => onSelect?.(user)}
    >
      <Avatar src={user.avatar} />
      <h3>{user.name}</h3>
      {isHovered && <p>{user.email}</p>}
    </div>
  );
}
```

**Composition pattern:**
```tsx
// Compound components
<Card>
  <Card.Header>Title</Card.Header>
  <Card.Body>Content</Card.Body>
  <Card.Footer>Actions</Card.Footer>
</Card>

// Render props
<DataFetcher url="/api/users">
  {({ data, loading, error }) => (
    loading ? <Spinner /> : <UserList users={data} />
  )}
</DataFetcher>
```

### State Management

**Local state (useState/useReducer):**
```tsx
// Simple state
const [count, setCount] = useState(0);

// Complex state with reducer
const [state, dispatch] = useReducer(reducer, initialState);
dispatch({ type: 'INCREMENT' });
```

**Global state (Zustand - lightweight):**
```tsx
import { create } from 'zustand';

interface AuthStore {
  user: User | null;
  login: (user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  login: (user) => set({ user }),
  logout: () => set({ user: null }),
}));
```

### Data Fetching

**TanStack Query (recommended):**
```tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

// Fetching
const { data, isLoading, error } = useQuery({
  queryKey: ['users', userId],
  queryFn: () => fetchUser(userId),
  staleTime: 5 * 60 * 1000, // 5 minutes
});

// Mutations
const queryClient = useQueryClient();
const mutation = useMutation({
  mutationFn: updateUser,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['users'] });
  },
});
```

### Next.js App Router

**Server Components (default):**
```tsx
// app/users/page.tsx - Server Component
async function UsersPage() {
  const users = await fetchUsers(); // Direct async/await
  return <UserList users={users} />;
}
```

**Client Components:**
```tsx
'use client';

// Required for: useState, useEffect, event handlers, browser APIs
export function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
}
```

**Server Actions:**
```tsx
// app/actions.ts
'use server';

export async function createUser(formData: FormData) {
  const name = formData.get('name');
  await db.users.create({ name });
  revalidatePath('/users');
}
```

### Vue 3 Composition API

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';

interface Props {
  initialCount?: number;
}

const props = withDefaults(defineProps<Props>(), {
  initialCount: 0,
});

const count = ref(props.initialCount);
const doubled = computed(() => count.value * 2);

const increment = () => count.value++;

onMounted(() => {
  console.log('Component mounted');
});
</script>

<template>
  <button @click="increment">
    Count:  (doubled: )
  </button>
</template>
```

### Error Handling

**Error Boundary (React):**
```tsx
class ErrorBoundary extends React.Component<Props, State> {
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return <ErrorFallback error={this.state.error} />;
    }
    return this.props.children;
  }
}
```

**Next.js error.tsx:**
```tsx
'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div>
      <h2>Something went wrong!</h2>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

## Advanced

### Performance Optimization

**React.memo for expensive renders:**
```tsx
const ExpensiveComponent = React.memo(function Expensive({ data }) {
  // Only re-renders if data changes (shallow comparison)
  return <ComplexVisualization data={data} />;
});
```

**useMemo/useCallback:**
```tsx
// Memoize expensive computations
const sortedItems = useMemo(
  () => items.sort((a, b) => a.name.localeCompare(b.name)),
  [items]
);

// Memoize callbacks for child components
const handleClick = useCallback((id: string) => {
  dispatch({ type: 'SELECT', id });
}, [dispatch]);
```

**Code splitting:**
```tsx
// Lazy load components
const Dashboard = lazy(() => import('./Dashboard'));

function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Dashboard />
    </Suspense>
  );
}
```

### Testing

**Component testing (Testing Library):**
```tsx
import { render, screen, fireEvent } from '@testing-library/react';

test('increments counter', async () => {
  render(<Counter />);

  const button = screen.getByRole('button');
  expect(button).toHaveTextContent('0');

  await fireEvent.click(button);
  expect(button).toHaveTextContent('1');
});
```

**E2E testing (Playwright):**
```ts
test('user can log in', async ({ page }) => {
  await page.goto('/login');
  await page.fill('[name=email]', 'user@example.com');
  await page.fill('[name=password]', 'password');
  await page.click('button[type=submit]');

  await expect(page).toHaveURL('/dashboard');
});
```

### Accessibility

- Use semantic HTML (`<button>`, `<nav>`, `<main>`)
- Add ARIA labels where needed
- Ensure keyboard navigation
- Test with screen readers
- Maintain color contrast ratios

```tsx
<button
  aria-label="Close modal"
  aria-expanded={isOpen}
  onClick={onClose}
>
  <CloseIcon aria-hidden="true" />
</button>
```

## Resources

- [React Docs](https://react.dev/)
- [Next.js Docs](https://nextjs.org/docs)
- [Vue.js Docs](https://vuejs.org/guide/)
- [TanStack Query](https://tanstack.com/query)
- [Tailwind CSS](https://tailwindcss.com/)
- [Testing Library](https://testing-library.com/)