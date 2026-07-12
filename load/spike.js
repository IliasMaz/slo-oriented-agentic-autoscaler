import http from "k6/http";
import { sleep } from "k6";

// Spike profile:
// Starts calm, spikes aggressively, then returns to baseline.
// Useful for testing fast scale-up and stabilization behavior.

export const options = {
  stages: [
    { duration: "45s", target: 8 },
    { duration: "20s", target: 80 },
    { duration: "1m", target: 80 },
    { duration: "30s", target: 10 },
    { duration: "45s", target: 10 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.08);
}
