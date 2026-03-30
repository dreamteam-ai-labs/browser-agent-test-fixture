import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'

// Mock next/navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({ push: mockPush }),
}))

// Mock next/link
jest.mock('next/link', () => {
  return function MockLink({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
    return <a href={href} className={className}>{children}</a>
  }
})

import Sidebar from '../components/Sidebar'

describe('Sidebar', () => {
  beforeEach(() => {
    mockPush.mockClear()
    localStorage.clear()
  })

  it('renders navigation links', () => {
    render(<Sidebar />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Projects')).toBeInTheDocument()
    expect(screen.getByText('Tasks')).toBeInTheDocument()
  })

  it('renders logout button', () => {
    render(<Sidebar />)
    expect(screen.getByText('Logout')).toBeInTheDocument()
  })

  it('clears token and redirects on logout', () => {
    localStorage.setItem('token', 'test-token')
    render(<Sidebar />)
    fireEvent.click(screen.getByText('Logout'))
    expect(localStorage.getItem('token')).toBeNull()
    expect(mockPush).toHaveBeenCalledWith('/login')
  })

  it('highlights the active route', () => {
    render(<Sidebar />)
    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink).toHaveClass('bg-blue-50')
  })
})
