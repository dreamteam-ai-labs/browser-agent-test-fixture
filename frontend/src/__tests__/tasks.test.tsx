import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'

jest.mock('next/navigation', () => ({
  usePathname: () => '/tasks',
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

import TasksPage from '../app/tasks/page'

const sampleTasks = [
  { id: 1, title: 'Fix bug', status: 'in_progress', project_id: 1 },
  { id: 2, title: 'Write tests', status: 'done', project_id: null },
]

describe('TasksPage', () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({ data: sampleTasks })
    mockDelete.mockResolvedValue({ data: {} })
  })

  afterEach(() => {
    mockGet.mockReset()
    mockDelete.mockReset()
  })

  it('renders Tasks heading', () => {
    render(<TasksPage />)
    expect(screen.getByText('Tasks')).toBeInTheDocument()
  })

  it('shows a New Task link', () => {
    render(<TasksPage />)
    const link = screen.getByText('New Task').closest('a')
    expect(link).toHaveAttribute('href', '/tasks/new')
  })

  it('renders task titles from API', async () => {
    render(<TasksPage />)
    await waitFor(() => {
      expect(screen.getByText('Fix bug')).toBeInTheDocument()
      expect(screen.getByText('Write tests')).toBeInTheDocument()
    })
  })

  it('shows empty state when no tasks', async () => {
    mockGet.mockResolvedValueOnce({ data: [] })
    render(<TasksPage />)
    await waitFor(() => {
      expect(screen.getByText(/No tasks yet/)).toBeInTheDocument()
    })
  })

  it('deletes a task when Delete is clicked', async () => {
    render(<TasksPage />)
    await waitFor(() => screen.getByText('Fix bug'))
    const deleteButtons = screen.getAllByText('Delete')
    fireEvent.click(deleteButtons[0])
    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('/api/tasks/1')
    })
  })

  it('displays task status badges', async () => {
    render(<TasksPage />)
    await waitFor(() => {
      expect(screen.getByText('in_progress')).toBeInTheDocument()
      expect(screen.getByText('done')).toBeInTheDocument()
    })
  })
})
