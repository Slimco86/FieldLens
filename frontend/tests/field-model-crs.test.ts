import { describe, expect, it } from "vitest";
import { crsKey } from "../src/features/scene/fieldModel";

describe("crsKey", () => {
  it("treats two spellings of the same stated UTM zone and datum as one frame", () => {
    const a = crsKey("Map-Zone: Zone 31N (0 E to 6 E); Geo Datum: European 1950 - Mean");
    const b = crsKey("Universal Transverse Mercator European 1950 - Mean Zone 31N (0 E to 6 E)");
    expect(a).toBe(b);
  });
  it("keeps different zones or datum names distinct", () => {
    const base = crsKey("ED50 / UTM zone 31N");
    expect(crsKey("ED50 / UTM zone 32N")).not.toBe(base);
    expect(crsKey("WGS 84 / UTM zone 31N")).not.toBe(base);
    expect(crsKey("Map-Zone: Zone 31N; Geo Datum: European 1950 - Mean")).not.toBe(crsKey("Map-Zone: Zone 31N; Geo Datum: WGS 84"));
  });
});
