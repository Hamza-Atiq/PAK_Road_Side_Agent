// Client-side E.164 phone validation using libphonenumber-js.

import { parsePhoneNumberFromString } from "libphonenumber-js";

export function normalizePhone(raw: string): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  // Always require an international prefix; libphonenumber will infer region.
  const parsed = parsePhoneNumberFromString(
    trimmed.startsWith("+") ? trimmed : `+${trimmed}`
  );
  if (!parsed || !parsed.isPossible()) return null;
  return parsed.number; // E.164
}
