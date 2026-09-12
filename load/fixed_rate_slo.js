import http from "k6/http";

// Fixed-arrival profile: both controllers receive the same request schedule.
// This separates controller behavior from closed-loop VU throughput effects.
export const options = {
  scenarios: {
    fixed_rate: {
      executor: "constant-arrival-rate",
      rate: 200,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 240,
      maxVUs: 400,
    },
  },
};

export default function () {
  http.get("http://localhost:8000/");
}
