import { Building2, Home } from 'lucide-react';
import type { ChangeEvent, JSX } from 'react';
import { AuthField } from './AuthField.tsx';
import type { CareSetupErrors, CareSetting, SignUpValues } from './authValidation.ts';

export function SignUpCareStep({
  values,
  errors,
  onFieldChange,
}: {
  values: SignUpValues;
  errors: CareSetupErrors;
  onFieldChange: (field: keyof SignUpValues, value: string | boolean) => void;
}): JSX.Element {
  const fieldChange = (event: ChangeEvent<HTMLInputElement>): void => onFieldChange('locationLabel', event.target.value);
  return (
    <section className="auth-step-content" aria-labelledby="care-step-title">
      <fieldset className="auth-setting-fieldset">
        <legend id="care-step-title">Where will you use it? <span className="auth-optional">Optional</span></legend>
        <div className="auth-setting-grid">
          <SettingChoice
            value="home"
            label="Home"
            description="A family care setup"
            icon={<Home />}
            selected={values.careSetting === 'home'}
            onSelect={() => onFieldChange('careSetting', 'home')}
          />
          <SettingChoice
            value="facility"
            label="Facility"
            description="A care team setup"
            icon={<Building2 />}
            selected={values.careSetting === 'facility'}
            onSelect={() => onFieldChange('careSetting', 'facility')}
          />
        </div>
        {errors.careSetting ? <p className="auth-field-error" role="alert">{errors.careSetting}</p> : null}
      </fieldset>
      <AuthField
        id="location-label"
        label="Home or facility name"
        value={values.locationLabel}
        onChange={fieldChange}
        placeholder="e.g. Sunrise Care Home"
        autoComplete="off"
      />
      <p className="auth-field-hint">Shown under your name in the dashboard.</p>
    </section>
  );
}

function SettingChoice({
  value,
  label,
  description,
  icon,
  selected,
  onSelect,
}: {
  value: Exclude<CareSetting, ''>;
  label: string;
  description: string;
  icon: JSX.Element;
  selected: boolean;
  onSelect: () => void;
}): JSX.Element {
  return (
    <label className={`auth-setting-choice${selected ? ' is-selected' : ''}`}>
      <input type="radio" name="care-setting" value={value} checked={selected} onChange={onSelect} />
      <span className="auth-setting-icon" aria-hidden="true">{icon}</span>
      <span><strong>{label}</strong><small>{description}</small></span>
      <span className="auth-role-check" aria-hidden="true" />
    </label>
  );
}
