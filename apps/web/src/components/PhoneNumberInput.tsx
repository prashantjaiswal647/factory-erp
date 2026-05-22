import { findPhoneCountry, localPhoneDigits, phoneCountries } from "../lib/phoneCountries";

type PhoneNumberInputProps = {
  countryCode: string;
  localNumber: string;
  label?: string;
  disabled?: boolean;
  required?: boolean;
  onCountryCodeChange: (value: string) => void;
  onLocalNumberChange: (value: string) => void;
};

export default function PhoneNumberInput({
  countryCode,
  disabled = false,
  label = "Mobile Number",
  localNumber,
  onCountryCodeChange,
  onLocalNumberChange,
  required = true
}: PhoneNumberInputProps) {
  const country = findPhoneCountry(countryCode);

  return (
    <label className="block text-sm">
      {label ? <span className="font-semibold text-[#111827]">{label}</span> : null}
      <div data-testid="phone-number-input" className={`${label ? "mt-1" : ""} grid min-h-11 grid-cols-10 gap-0 overflow-hidden rounded-lg border border-[#E5E7EB] bg-white focus-within:border-[#6D28D9] focus-within:ring-2 focus-within:ring-indigo-600`}>
        <div className="col-span-3 min-w-[90px] border-r border-[#E5E7EB] bg-[#FFF7ED]">
          <select
            aria-label="Country code"
            data-testid="country-code-select"
            className="h-full w-full truncate bg-transparent px-2 text-sm font-semibold text-[#111827] outline-none disabled:bg-zinc-100 sm:px-3"
            disabled={disabled}
            value={country.dialCode}
            onChange={(event) => onCountryCodeChange(event.target.value)}
          >
            {phoneCountries.map((item) => (
              <option key={item.code} value={item.dialCode}>
                {item.flag} {item.name} ({item.dialCode})
              </option>
            ))}
          </select>
        </div>
        <div className="col-span-7 min-w-0 bg-white">
          <input
            autoComplete="tel-national"
            data-testid="mobile-number-input"
            className="h-full min-w-0 w-full bg-transparent px-3 text-sm font-medium text-[#111827] outline-none placeholder:text-[#9CA3AF] disabled:bg-zinc-50"
            disabled={disabled}
            inputMode="tel"
            maxLength={country.maxLength}
            placeholder="Mobile Number"
            required={required}
            type="tel"
            value={localNumber}
            onChange={(event) => onLocalNumberChange(localPhoneDigits(event.target.value))}
          />
        </div>
      </div>
    </label>
  );
}
