import { Check, ChevronDown } from 'lucide-react';
import {
  useEffect,
  useId,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import './SelectDropdown.css';

export interface SelectOption<T = string> {
  value: T;
  label: string;
  icon?: ReactNode;
  hint?: string;
  disabled?: boolean;
}

export interface SelectDropdownProps<T extends string | number = string> {
  id?: string;
  label?: string;
  ariaLabel?: string;
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  icon?: ReactNode;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  size?: 'sm' | 'md';
  align?: 'left' | 'right';
  width?: string | number;
}

export function SelectDropdown<T extends string | number = string>({
  id: customId,
  label,
  ariaLabel,
  value,
  options,
  onChange,
  icon,
  placeholder,
  disabled = false,
  className = '',
  size = 'md',
  align = 'left',
  width,
}: SelectDropdownProps<T>): JSX.Element {
  const generatedId = useId();
  const id = customId || generatedId;
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

  const openDropdown = () => {
    setIsOpen(true);
    const selectedIdx = options.findIndex((opt) => opt.value === value);
    setHighlightedIndex(selectedIdx >= 0 ? selectedIdx : 0);
  };

  const closeDropdown = () => {
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  // Close when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null;
      if (!target || !containerRef.current) return;
      if (!containerRef.current.contains(target)) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [isOpen]);

  // Keyboard navigation
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement | HTMLDivElement>) => {
    if (disabled) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!isOpen) {
        openDropdown();
      } else {
        setHighlightedIndex((prev) => {
          let next = prev + 1;
          while (next < options.length && options[next]?.disabled) {
            next++;
          }
          return next < options.length ? next : prev;
        });
      }
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (!isOpen) {
        openDropdown();
      } else {
        setHighlightedIndex((prev) => {
          let next = prev - 1;
          while (next >= 0 && options[next]?.disabled) {
            next--;
          }
          return next >= 0 ? next : prev;
        });
      }
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (!isOpen) {
        openDropdown();
      } else if (highlightedIndex >= 0 && options[highlightedIndex] && !options[highlightedIndex].disabled) {
        onChange(options[highlightedIndex].value);
        closeDropdown();
        triggerRef.current?.focus();
      }
    } else if (event.key === 'Escape') {
      if (isOpen) {
        event.preventDefault();
        closeDropdown();
        triggerRef.current?.focus();
      }
    } else if (event.key === 'Tab') {
      if (isOpen) {
        closeDropdown();
      }
    }
  };

  const handleSelect = (optionValue: T) => {
    onChange(optionValue);
    closeDropdown();
    triggerRef.current?.focus();
  };

  return (
    <div
      ref={containerRef}
      className={`select-dropdown-container ${className}${isOpen ? ' is-open' : ''}${disabled ? ' is-disabled' : ''}`}
      style={width ? { width } : undefined}
    >
      {/* Hidden native select keeps screen reader semantics & test assertions intact */}
      <select
        id={id}
        aria-label={ariaLabel || label}
        value={String(value)}
        disabled={disabled}
        tabIndex={-1}
        className="select-dropdown-hidden-select"
        onChange={(event) => {
          const match = options.find((opt) => String(opt.value) === event.target.value);
          if (match) onChange(match.value);
        }}
      >
        {options.map((opt) => (
          <option key={String(opt.value)} value={String(opt.value)} disabled={opt.disabled}>
            {opt.label}
          </option>
        ))}
      </select>

      <button
        ref={triggerRef}
        type="button"
        id={`${id}-trigger`}
        className={`select-dropdown-trigger select-dropdown-trigger-${size}${isOpen ? ' is-active' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={`${id}-menu`}
        disabled={disabled}
        onClick={() => (isOpen ? closeDropdown() : openDropdown())}
        onKeyDown={handleKeyDown}
      >
        {icon ? <span className="select-dropdown-lead-icon" aria-hidden="true">{icon}</span> : null}
        <span className="select-dropdown-label-text">
          {selectedOption ? selectedOption.label : placeholder || 'Select…'}
        </span>
        <ChevronDown className="select-dropdown-chevron" aria-hidden="true" />
      </button>

      {isOpen && (
        <div
          ref={menuRef}
          id={`${id}-menu`}
          className={`select-dropdown-menu select-dropdown-align-${align}`}
          role="listbox"
          tabIndex={-1}
          aria-activedescendant={highlightedIndex >= 0 ? `${id}-opt-${highlightedIndex}` : undefined}
          onKeyDown={handleKeyDown}
        >
          {options.map((opt, idx) => {
            const isSelected = opt.value === value;
            const isHighlighted = idx === highlightedIndex;

            return (
              <button
                type="button"
                key={String(opt.value)}
                id={`${id}-opt-${idx}`}
                role="option"
                aria-selected={isSelected}
                disabled={opt.disabled}
                className={`select-dropdown-item${isSelected ? ' is-selected' : ''}${isHighlighted ? ' is-highlighted' : ''}${opt.disabled ? ' is-disabled' : ''}`}
                onClick={() => handleSelect(opt.value)}
                onMouseEnter={() => setHighlightedIndex(idx)}
              >
                {opt.icon ? <span className="select-dropdown-item-icon" aria-hidden="true">{opt.icon}</span> : null}
                <span className="select-dropdown-item-content">
                  <span className="select-dropdown-item-title">{opt.label}</span>
                  {opt.hint ? <span className="select-dropdown-item-hint">{opt.hint}</span> : null}
                </span>
                {isSelected ? <Check className="select-dropdown-item-check" aria-hidden="true" /> : null}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
