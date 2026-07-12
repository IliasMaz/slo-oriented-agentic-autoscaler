import http from "k6/http";
import { sleep } from "k6";

// Ramp profile:
// Gradually increases traffic, holds, then decreases.
// Good for observing whether the autoscaler reacts smoothly to a rising trend.

export const options = {
  stages: [
    { duration: "1m", target: 5 },
    { duration: "2m", target: 25 },
    { duration: "2m", target: 45 },
    { duration: "1m", target: 20 },
    { duration: "1m", target: 5 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.15);
}
