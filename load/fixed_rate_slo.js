import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const httpStatusErrors = new Counter("http_status_errors");
const transportErrors = new Counter("transport_errors");

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
  const response = http.get("http://localhost:8000/");
  if (response.status === 0) {
    transportErrors.add(1);
  } else if (response.status < 200 || response.status >= 300) {
    httpStatusErrors.add(1);
  }
  check(response, {
    "application returned 2xx": (result) =>
      result.status >= 200 && result.status < 300,
  });
}
