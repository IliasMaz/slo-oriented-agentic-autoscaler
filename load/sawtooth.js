import http from "k6/http";
import { sleep } from "k6";

// Sawtooth profile:
// Repeats gradual climb and drop cycles.
// Good for checking how the autoscaler handles repeated oscillations.

export const options = {
  stages: [
    { duration: "45s", target: 10 },
    { duration: "45s", target: 30 },
    { duration: "45s", target: 50 },
    { duration: "45s", target: 15 },
    { duration: "45s", target: 35 },
    { duration: "45s", target: 5 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.12);
}
