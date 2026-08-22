import { describe, expect, it } from "vitest";

import { unknownMs, unknownNumber, unknownPercent } from "@/lib/unknown";

describe("unknown vs zero", () => {
  it("keeps reported zero", () => {
    expect(unknownNumber(0)).toBe("0");
    expect(unknownPercent(0)).toBe("0%");
    expect(unknownMs(0)).toBe("0ms");
  });

  it("does not coerce missing values to zero", () => {
    expect(unknownNumber(null)).toBe("—");
    expect(unknownPercent(undefined)).toBe("—");
    expect(unknownMs(null)).toBe("—");
  });
});
