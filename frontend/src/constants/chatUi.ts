export const EMPTY_STATE_CONTENT = {
  heading: "Welcome to Tailored.ai",
  sub: "Add a video, PDF, or document to your library, then get answers grounded in that content - not generic AI responses.",
};

export const EMPTY_STATE_STEPS = [
  {
    title: "Add a source",
    desc: "Paste a YouTube URL or upload a file using the Sources panel on the right",
  },
  {
    title: "Wait for processing",
    desc: "Usually under a minute - a green dot appears when your source is ready",
  },
  {
    title: "Start asking",
    desc: "Get answers with timestamps and direct links back to the source",
  },
] as const;

export const DEFAULT_SESSION_TITLE = "New session";
