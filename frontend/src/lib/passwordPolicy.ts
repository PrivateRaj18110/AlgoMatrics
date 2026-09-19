import { z } from "zod";

// Mirrors validate_password_strength() on the server so people see the rules
// before submitting rather than after.
export const PASSWORD_RULES = [
  { label: "At least 10 characters", test: (value: string) => value.length >= 10 },
  {
    label: "Upper- and lower-case letters",
    test: (value: string) => value.toLowerCase() !== value && value.toUpperCase() !== value,
  },
  { label: "At least one number", test: (value: string) => /\d/.test(value) },
];

export const newPasswordSchema = z
  .string()
  .max(200)
  .refine((value) => PASSWORD_RULES.every((rule) => rule.test(value)), {
    message: "Password does not meet the requirements",
  });
