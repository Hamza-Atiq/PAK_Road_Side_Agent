import { parsePhoneNumberFromString } from "libphonenumber-js";

export function normalizePhone(raw: string): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  const parsed = parsePhoneNumberFromString(
    trimmed.startsWith("+") ? trimmed : `+${trimmed}`
  );
  if (!parsed || !parsed.isPossible()) return null;
  return parsed.number;
}
