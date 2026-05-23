import React, { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

interface PasswordInputProps {
  id?: string;
  name?: string;
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  autoComplete?: string;
  error?: string;
  "data-testid"?: string;
  className?: string;
  leftIcon?: React.ComponentType<any>;
}

export default function PasswordInput({
  id,
  name,
  label,
  value,
  onChange,
  placeholder,
  required = false,
  disabled = false,
  autoComplete,
  error,
  "data-testid": dataTestId,
  className = "",
  leftIcon: LeftIcon,
}: PasswordInputProps) {
  const [showPassword, setShowPassword] = useState(false);
  const inputId = id || `password-input-${(name || label || dataTestId || "").toLowerCase().replace(/[^a-z0-9]+/g, "-") || Math.random().toString(36).substr(2, 9)}`;

  return (
    <div className={`flex flex-col gap-1.5 ${className}`} data-testid={dataTestId}>
      {label && (
        <label htmlFor={inputId} className="text-sm font-semibold text-[#111827]">
          {label}
        </label>
      )}
      <div className="relative w-full">
        {LeftIcon && (
          <LeftIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
        )}
        <input
          id={inputId}
          name={name}
          type={showPassword ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          autoComplete={autoComplete}
          className={`h-11 w-full rounded-lg border bg-white text-sm text-[#111827] outline-none transition placeholder:text-[#9CA3AF] focus:border-[#6D28D9] focus:ring-2 focus:ring-[#F3E8FF] disabled:cursor-not-allowed disabled:bg-zinc-100 ${
            error ? "border-red-500 focus:border-red-500 focus:ring-red-100" : "border-[#E5E7EB] focus:border-[#6D28D9]"
          } ${LeftIcon ? "pl-9" : "pl-3"} pr-10`}
        />
        <button
          type="button"
          tabIndex={0}
          onClick={() => setShowPassword((prev) => !prev)}
          disabled={disabled}
          data-testid="password-toggle"
          aria-label={showPassword ? "Hide password" : "Show password"}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 focus:outline-none focus:text-zinc-600 disabled:cursor-not-allowed"
        >
          {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
        </button>
      </div>
      {error && <p className="text-xs font-medium text-red-600">{error}</p>}
    </div>
  );
}
