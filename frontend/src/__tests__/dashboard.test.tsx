import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({ push: jest.fn() }),
}))

jest.mock('next/link', () => {
  return function MockLink({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
    return <a href={href} className={className}>{children}</a>
  }
})

const mockGet = jest.fn()

// Mock the API module
jest.mock('../lib/api', () => ({
  __esModule: true,
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: jest.fn(),
    delete: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  },
}))

// Mock AuthGuard to render children directly
jest.mock('../components/AuthGuard', () => {
  return function MockAuthGuard({ children }: { children: React.ReactNode }) {
    return <>{children}</>
  }
})

// Mock Sidebar
jest.mock('../components/Sidebar', () => {
  return function MockSidebar() {
    return <nav data-testid="sidebar">Sidebar</nav>
  }
})

import DashboardPage from '../app/dashboard/page'

describe('DashboardPage', () => {
  beforeEach(() => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/api/auth/me') return Promise.resolve({ data: { id: 1, email: 'test@example.com', display_name: 'Test User' } })
      if (url === '/api/projects') return Promise.resolve({ data: [{ id: 1 }, { id: 2 }] })
      if (url === '/api/tasks') return Promise.resolve({ data: [{ id: 1 }] })
      return Promise.resolve({ data: [] })
    })
  })

  afterEach(() => {
    mockGet.mockReset()
  })

  it('renders Dashboard heading', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('shows project and task counts after loading', async () => {
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument() // project count
      expect(screen.getByText('1')).toBeInTheDocument() // task count
    })
  })

  it('shows welcome message with user display name', async () => {
    render(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText(/Welcome back, Test User/)).toBeInTheDocument()
    })
  })

  it('renders Projects and Tasks stat cards', () => {
    render(<DashboardPage />)
    expect(screen.getByText('Projects')).toBeInTheDocument()
    expect(screen.getByText('Tasks')).toBeInTheDocument()
  })
})
