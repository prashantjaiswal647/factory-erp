export type PhoneCountry = {
  code: string;
  name: string;
  dialCode: string;
  flag: string;
  minLength: number;
  maxLength: number;
};

export const phoneCountries: PhoneCountry[] = [
  { code: "IN", name: "India", dialCode: "+91", flag: "🇮🇳", minLength: 10, maxLength: 10 },
  { code: "US", name: "United States", dialCode: "+1", flag: "🇺🇸", minLength: 10, maxLength: 10 },
  { code: "GB", name: "United Kingdom", dialCode: "+44", flag: "🇬🇧", minLength: 10, maxLength: 10 },
  { code: "AE", name: "UAE", dialCode: "+971", flag: "🇦🇪", minLength: 9, maxLength: 9 }
];

export const defaultPhoneCountry = phoneCountries[0];

export function findPhoneCountry(dialCode: string) {
  return phoneCountries.find((country) => country.dialCode === dialCode) || defaultPhoneCountry;
}

export function localPhoneDigits(value: string) {
  return value.replace(/\D/g, "");
}

export function validateLocalPhone(dialCode: string, localNumber: string) {
  const country = findPhoneCountry(dialCode);
  const digits = localPhoneDigits(localNumber);
  return digits.length >= country.minLength && digits.length <= country.maxLength;
}

export function toE164Phone(dialCode: string, localNumber: string) {
  return `${findPhoneCountry(dialCode).dialCode}${localPhoneDigits(localNumber)}`;
}

export function splitE164Phone(value?: string | null) {
  if (!value) return { country: defaultPhoneCountry, localNumber: "" };
  const compact = value.replace(/\s/g, "");
  const country = [...phoneCountries]
    .sort((a, b) => b.dialCode.length - a.dialCode.length)
    .find((item) => compact.startsWith(item.dialCode)) || defaultPhoneCountry;
  return {
    country,
    localNumber: localPhoneDigits(compact.slice(country.dialCode.length))
  };
}
