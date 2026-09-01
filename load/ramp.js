import http from "k6/http";
import { sleep } from "k6";

// Ramp profile:
// Gradually increases traffic, holds, then decreases.
// Good for observing whether the autoscaler reacts smoothly to a rising trend.

export const options = {
  stages: [
    { duration: "1m", target: 10 },
    { duration: "2m", target: 50 },
    { duration: "2m", target: 90 },
    { duration: "1m", target: 40 },
    { duration: "1m", target: 10 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.15);
}
