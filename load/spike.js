import http from "k6/http";
import { sleep } from "k6";

// Spike profile:
// Starts calm, spikes aggressively, then returns to baseline.
// Useful for testing fast scale-up and stabilization behavior.

export const options = {
  stages: [
    { duration: "45s", target: 150 },
    { duration: "30s", target: 600 },
    { duration: "1m", target: 60 },
    { duration: "30s", target: 20 },
    { duration: "45s", target: 200 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.08);
}
