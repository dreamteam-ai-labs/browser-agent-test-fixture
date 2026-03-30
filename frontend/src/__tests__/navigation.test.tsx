import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  usePathname: () => '/projects',
  useRouter: () => ({ push: jest.fn() }),
}))

jest.mock('next/link', () => {
  return function MockLink({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
    return <a href={href} className={className}>{children}</a>
  }
})

import Sidebar from '../components/Sidebar'

describe('Navigation route highlighting', () => {
  it('highlights /projects as active when on projects page', () => {
    render(<Sidebar />)
    const projectsLink = screen.getByText('Projects').closest('a')
    expect(projectsLink).toHaveClass('bg-blue-50')
    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink).not.toHaveClass('bg-blue-50')
  })

  it('has correct hrefs for all nav items', () => {
    render(<Sidebar />)
    expect(screen.getByText('Dashboard').closest('a')).toHaveAttribute('href', '/dashboard')
    expect(screen.getByText('Projects').closest('a')).toHaveAttribute('href', '/projects')
    expect(screen.getByText('Tasks').closest('a')).toHaveAttribute('href', '/tasks')
  })
})
