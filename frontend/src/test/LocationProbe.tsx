import type { ReactElement } from 'react';
import { useLocation } from 'react-router-dom';

/** Exposes the current route so tests can assert navigation and URL state. */
export function LocationProbe(): ReactElement {
  const location = useLocation();
  return <output aria-label="location">{`${location.pathname}${location.search}`}</output>;
}
