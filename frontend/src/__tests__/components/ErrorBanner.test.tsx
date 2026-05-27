import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ErrorBanner } from '../../components/ErrorBanner';

describe('ErrorBanner', () => {
  it('renders the error title for api_key_invalid variant', () => {
    render(<ErrorBanner variant="api_key_invalid" />);
    expect(screen.getByText(/ai provider key invalid/i)).toBeInTheDocument();
  });

  it('renders custom message when provided', () => {
    render(<ErrorBanner variant="scraper_failure" message="Custom error details" />);
    expect(screen.getByText('Custom error details')).toBeInTheDocument();
  });

  it('calls onDismiss when dismiss button is clicked', async () => {
    const onDismiss = vi.fn();
    render(<ErrorBanner variant="api_key_invalid" onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('does not render a dismiss button when onDismiss is not provided', () => {
    render(<ErrorBanner variant="no_matching_jobs" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
