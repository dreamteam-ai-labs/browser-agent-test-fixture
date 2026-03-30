import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'

jest.mock('next/navigation', () => ({
  usePathname: () => '/projects',
  useRouter: () => ({ push: jest.fn() }),
}))

jest.mock('next/link', () => {
  return function MockLink({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
    return <a href={href} className={className}>{children}</a>
  }
})

const mockGet = jest.fn()
const mockDelete = jest.fn()

jest.mock('../lib/api', () => ({
  __esModule: true,
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    post: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  },
}))

jest.mock('../components/AuthGuard', () => {
  return function MockAuthGuard({ children }: { children: React.ReactNode }) {
    return <>{children}</>
  }
})

jest.mock('../components/Sidebar', () => {
  return function MockSidebar() {
    return <nav data-testid="sidebar">Sidebar</nav>
  }
})

import ProjectsPage from '../app/projects/page'

const sampleProjects = [
  { id: 1, name: 'Alpha', description: 'First project', color: '#3B82F6' },
  { id: 2, name: 'Beta', description: 'Second project', color: '#10B981' },
]

describe('ProjectsPage', () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({ data: sampleProjects })
    mockDelete.mockResolvedValue({ data: {} })
  })

  afterEach(() => {
    mockGet.mockReset()
    mockDelete.mockReset()
  })

  it('renders Projects heading', () => {
    render(<ProjectsPage />)
    expect(screen.getByText('Projects')).toBeInTheDocument()
  })

  it('shows a New Project link', () => {
    render(<ProjectsPage />)
    const link = screen.getByText('New Project').closest('a')
    expect(link).toHaveAttribute('href', '/projects/new')
  })

  it('renders project names from API', async () => {
    render(<ProjectsPage />)
    await waitFor(() => {
      expect(screen.getByText('Alpha')).toBeInTheDocument()
      expect(screen.getByText('Beta')).toBeInTheDocument()
    })
  })

  it('shows empty state when no projects', async () => {
    mockGet.mockResolvedValueOnce({ data: [] })
    render(<ProjectsPage />)
    await waitFor(() => {
      expect(screen.getByText(/No projects yet/)).toBeInTheDocument()
    })
  })

  it('deletes a project when Delete is clicked', async () => {
    render(<ProjectsPage />)
    await waitFor(() => screen.getByText('Alpha'))
    const deleteButtons = screen.getAllByText('Delete')
    fireEvent.click(deleteButtons[0])
    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('/api/projects/1')
    })
  })
})
