import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Login } from './Login';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('Login Page Component', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('should render the login form inputs and elements', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/FIREOPS/i);
    expect(screen.getByText(/ACCESS SECURE TERMINAL/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Operator ID/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Authentication Token/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /INITIALIZE COMMAND LINK/i })).toBeInTheDocument();
  });

  it('should allow user typing into Operator ID and Token inputs', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const operatorInput = screen.getByLabelText(/Operator ID/i) as HTMLInputElement;
    const tokenInput = screen.getByLabelText(/Authentication Token/i) as HTMLInputElement;

    fireEvent.change(operatorInput, { target: { value: 'OP-44912' } });
    fireEvent.change(tokenInput, { target: { value: 'secret-token-123' } });

    expect(operatorInput.value).toBe('OP-44912');
    expect(tokenInput.value).toBe('secret-token-123');
  });

  it('should toggle password visibility when eye button is clicked', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const tokenInput = screen.getByLabelText(/Authentication Token/i) as HTMLInputElement;
    expect(tokenInput.type).toBe('password');

    const toggleBtn = screen.getByRole('button', { name: /Show password/i });
    fireEvent.click(toggleBtn);

    expect(tokenInput.type).toBe('text');

    const hideBtn = screen.getByRole('button', { name: /Hide password/i });
    fireEvent.click(hideBtn);

    expect(tokenInput.type).toBe('password');
  });

  it('should navigate to /dashboard on form submit', () => {
    const { container } = render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const operatorInput = screen.getByLabelText(/Operator ID/i);
    const tokenInput = screen.getByLabelText(/Authentication Token/i);

    fireEvent.change(operatorInput, { target: { value: 'OP-12345' } });
    fireEvent.change(tokenInput, { target: { value: 'pass123' } });

    const form = container.querySelector('form')!;
    fireEvent.submit(form);

    expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
  });
});
