// Observation only: never mutate FFmpeg arguments or renderer settings.
export function createDiagnostics() {
  const data = {
    units: "milliseconds",
    resolvedConcurrency: null,
    parallelEncoding: null,
    renderedDoneIn: null,
    encodedDoneIn: null,
    ffmpeg: [],
    fallback_reason: "unavailable: renderer exposes no fallback event",
    timing_note: "renderedDoneIn and encodedDoneIn are Remotion completion durations; may overlap, not additive",
  };
  return {
    data,
    onStart(info) {
      data.resolvedConcurrency = info.resolvedConcurrency;
      data.parallelEncoding = info.parallelEncoding;
    },
    onProgress(info) {
      for (const key of ["renderedDoneIn", "encodedDoneIn"]) {
        if (typeof info[key] === "number" && Number.isFinite(info[key]) && info[key] >= 0) {
          data[key] = info[key];
        }
      }
    },
    ffmpegOverride({type, args}) {
      const encoders = [];
      const inputs = [];
      const lastInput = args.lastIndexOf("-i");
      for (let i = 0; i < args.length - 1; i++) {
        if (i > lastInput && ["-c:v", "-vcodec", "-codec:v"].includes(args[i])) encoders.push(args[i + 1]);
        if (args[i] === "-f") inputs.push(args[i + 1]);
      }
      data.ffmpeg.push({type, video_encoders: encoders, format_flags: inputs,
        capture_mode: args.includes("image2pipe") ? "image2pipe" : args.includes("rawvideo") ? "rawvideo" : "unavailable"});
      return args;
    },
  };
}
