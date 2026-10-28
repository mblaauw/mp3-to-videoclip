// Opt-in experiments only. The empty default adds no production encoder flags.
export const BENCHMARK_PROFILE = "videotoolbox-20m";

export function benchmarkOptions(profile, kind) {
  if (profile == null) return {};
  if (profile !== BENCHMARK_PROFILE) throw new Error("unknown benchmark profile");
  if (kind !== "base") throw new Error("benchmark encoder profiles are base-only; graphics are unchanged");
  // Deliberately not quality-equivalent to libx264's default CRF policy.
  return {hardwareAcceleration: "required", videoBitrate: "20M"};
}
