/** US phone number input mask: strips non-digits, caps at 10, and formats
 * incrementally as the user types — "2125551234" -> "(212) 555-1234". */
export function formatPhoneInput(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 10);
  const len = digits.length;
  if (len === 0) return "";
  if (len < 4) return `(${digits}`;
  if (len < 7) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

export function phoneDigitCount(formatted: string): number {
  return formatted.replace(/\D/g, "").length;
}
