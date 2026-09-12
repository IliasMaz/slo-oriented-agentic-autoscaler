import http from "k6/http";
import { sleep } from "k6";

// Queueing-focused profile: the app performs small I/O-like work with no CPU
// burn or injected errors. At high concurrency, per-pod queueing should raise
// latency and in-progress requests, which the agentic controller observes.
export const options = {
  stages: [
    { duration: "30s", target: 30 },
    { duration: "30s", target: 240 },
    { duration: "2m", target: 240 },
    { duration: "30s", target: 30 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.05);
}
