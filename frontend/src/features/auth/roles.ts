/** One name per access level, used everywhere a role is shown. */
export function roleLabel(role: string | null | undefined): string {
  return role === 'admin' ? 'Admin' : 'Caregiver';
}
