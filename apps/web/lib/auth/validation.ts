/**
 * Lightweight, dependency-free auth field validators.
 * Each returns `null` on success or a human message on failure.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(value: string): string | null {
  const v = value.trim();
  if (!v) return "Email is required.";
  if (v.length > 254) return "Email is too long.";
  if (!EMAIL_RE.test(v)) return "Enter a valid email address.";
  return null;
}

export function validatePassword(value: string): string | null {
  if (!value) return "Password is required.";
  if (value.length < 8) return "Use at least 8 characters.";
  if (value.length > 128) return "Password is too long.";
  return null;
}

export function validateOtp(value: string): string | null {
  if (!value) return "Enter the 6-digit code.";
  if (!/^\d{6}$/.test(value)) return "Code must be 6 digits.";
  return null;
}

export type PasswordStrength = {
  /** 0..4 — used to drive segmented strength meter. */
  score: 0 | 1 | 2 | 3 | 4;
  label: "empty" | "weak" | "okay" | "good" | "strong";
  hint: string;
};

/**
 * Heuristic password strength (no zxcvbn dependency).
 * Scores entropy bands by length + character class diversity.
 */
export function passwordStrength(value: string): PasswordStrength {
  if (!value) {
    return { score: 0, label: "empty", hint: "8+ characters with mixed case and a number." };
  }

  let classes = 0;
  if (/[a-z]/.test(value)) classes++;
  if (/[A-Z]/.test(value)) classes++;
  if (/\d/.test(value)) classes++;
  if (/[^A-Za-z0-9]/.test(value)) classes++;

  const len = value.length;
  let raw = 0;
  if (len >= 8) raw++;
  if (len >= 12) raw++;
  if (len >= 16) raw++;
  raw += Math.max(0, classes - 1);

  const score = Math.min(4, Math.max(1, raw)) as 1 | 2 | 3 | 4;

  const labels = ["empty", "weak", "okay", "good", "strong"] as const;
  const hints: Record<number, string> = {
    1: "Add length and mix character types.",
    2: "Almost there — add length or a symbol.",
    3: "Solid. A symbol would push it to strong.",
    4: "Strong password.",
  };

  return { score, label: labels[score], hint: hints[score] };
}
