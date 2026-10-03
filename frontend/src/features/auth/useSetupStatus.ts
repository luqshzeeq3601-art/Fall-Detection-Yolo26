import { useEffect, useState } from 'react';
import { authApi } from '../../api/platform.ts';

/** True while initial admin setup is open, false once an admin exists, null while unknown. */
export function useSetupStatus(): boolean | null {
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    authApi.setupStatus().then(
      (result) => { if (active && typeof result?.needs_setup === 'boolean') setNeedsSetup(result.needs_setup); },
      () => undefined,
    );
    return () => { active = false; };
  }, []);
  return needsSetup;
}
