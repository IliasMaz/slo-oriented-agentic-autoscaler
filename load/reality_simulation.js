import http from "k6/http";
import { check, sleep } from "k6";

// Layer: load generation.
// Used for end-to-end
// autoscaler stress testing.
// Reality simulation profile:
// Emulates a day-like traffic pattern with warmup, peak, plateau, burst, and cooldown.
// Includes a small health-check percentage and variable think time.

export const options = {
  stages: [
    { duration: "1m", target: 5 },
    { duration: "2m", target: 15 },
    { duration: "1m", target: 35 },
    { duration: "1m", target: 20 },
    { duration: "2m", target: 28 },
    { duration: "45s", target: 50 },
    { duration: "1m", target: 18 },
    { duration: "1m", target: 8 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.08"],
    http_req_duration: ["p(95)<1500"],
  },
};

export default function () {
  const roll = Math.random();

  // 82% user traffic to root endpoint, 18% monitoring-like health probes.
  if (roll < 0.82) {
    const res = http.get("http://localhost:8000/");
    check(res, {
      "root status is 200 or 500": (r) => r.status === 200 || r.status === 500,
    });
  } else {
    const res = http.get("http://localhost:8000/health");
    check(res, {
      "health status is 200": (r) => r.status === 200,
    });
  }

  // Simulate human think time variability.
  const thinkTime = 0.06 + Math.random() * 0.34;
  sleep(thinkTime);
}
