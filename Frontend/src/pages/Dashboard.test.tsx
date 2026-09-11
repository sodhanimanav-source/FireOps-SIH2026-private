import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Dashboard } from './Dashboard';
import { useAppStore } from '../store/appStore';
import * as queries from '../api/queries';
import type { Facility, Hotspot } from '../types';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});


vi.mock('../components/Map/MapController', () => ({
  MapController: () => <div data-testid="mock-map-controller">Mock Map</div>,
}));

describe('Dashboard Page Component', () => {
  const mockFacilities: Facility[] = [
    {
      id: 'fac-101',
      name: 'Petro Refinery North',
      type: 'Petrochemical',
      latitude: 29.7604,
      longitude: -95.3698,
      buffer_radius_km: 7.5,
      baseline_frp: 15.2,
    },
  ];

  const mockHotspots: Hotspot[] = [
    {
      id: 'hot-501',
      latitude: 34.0522,
      longitude: -118.2437,
      frp: 88.4,
      temperature_k: 360.2,
      modified_z_score: 5.4,
      persistence_index: 0.92,
      classification: 'Flare Emission Anomaly',
    },
  ];

  beforeEach(() => {
    useAppStore.setState({
      selectedFacility: null,
      selectedHotspot: null,
      anomalyFilters: true,
    });
    vi.spyOn(queries, 'useFacilities').mockReturnValue({
      data: mockFacilities,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof queries.useFacilities>);
    vi.spyOn(queries, 'useHotspots').mockReturnValue({
      data: mockHotspots,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof queries.useHotspots>);
    mockNavigate.mockClear();
  });

  it('should render the dashboard layout with header, navigation, and map', () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    expect(screen.getByText(/FIREOPS/i)).toBeInTheDocument();
    expect(screen.getByText(/\.COMMAND/i)).toBeInTheDocument();
    expect(screen.getByText(/Vigilance Alpha-9/i)).toBeInTheDocument();
    expect(screen.getByText(/Live Telemetry/i)).toBeInTheDocument();
    expect(screen.getByTestId('mock-map-controller')).toBeInTheDocument();
  });

  it('should toggle anomaly filter state when checkbox switch is clicked', () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    const switchCheckbox = screen.getByRole('switch', { name: /Filter High Anomalies/i });
    expect(switchCheckbox).toBeChecked();

    fireEvent.click(switchCheckbox);
    expect(useAppStore.getState().anomalyFilters).toBe(false);

    fireEvent.click(switchCheckbox);
    expect(useAppStore.getState().anomalyFilters).toBe(true);
  });

  it('should display Hotspot Telemetry Panel with dynamic data when selectedHotspot is set', () => {
    useAppStore.setState({ selectedHotspot: 'hot-501', selectedFacility: null });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    expect(screen.getByTestId('hotspot-panel')).toBeInTheDocument();
    expect(screen.getByTestId('hotspot-id')).toHaveTextContent('ID: hot-501');
    expect(screen.getByTestId('hotspot-frp')).toHaveTextContent('88.4 MW');
    expect(screen.getByTestId('hotspot-temp')).toHaveTextContent('360.2 K');
    expect(screen.getByTestId('hotspot-zscore')).toHaveTextContent('5.4');
    expect(screen.getByTestId('hotspot-persistence')).toHaveTextContent('0.92');
    expect(screen.getByText(/Flare Emission Anomaly/i)).toBeInTheDocument();
  });

  it('should display Facility Telemetry Panel with dynamic data when selectedFacility is set', () => {
    useAppStore.setState({ selectedFacility: 'fac-101', selectedHotspot: null });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    expect(screen.getByTestId('facility-panel')).toBeInTheDocument();
    expect(screen.getByTestId('facility-id')).toHaveTextContent('ID: fac-101');
    expect(screen.getByTestId('facility-name')).toHaveTextContent('Petro Refinery North');
    expect(screen.getByTestId('facility-type')).toHaveTextContent('Petrochemical');
    expect(screen.getByTestId('facility-buffer')).toHaveTextContent('7.5 km');
    expect(screen.getByTestId('facility-baseline-frp')).toHaveTextContent('15.2 MW');
  });

  it('should clear selection when the close button on the telemetry panel is clicked', () => {
    useAppStore.setState({ selectedHotspot: 'hot-501', selectedFacility: null });

    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    const closeBtn = screen.getByLabelText(/Close telemetry panel/i);
    fireEvent.click(closeBtn);

    expect(useAppStore.getState().selectedHotspot).toBeNull();
    expect(useAppStore.getState().selectedFacility).toBeNull();
  });

  it('should navigate to login page on Log Out button click', () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    const logoutBtn = screen.getByRole('button', { name: /Log Out/i });
    fireEvent.click(logoutBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/');
  });
});
