import http from "k6/http";
import { sleep } from "k6";

// Burst load profile:
// Starts low, spikes to high traffic, then drops back down.
// Useful for testing autoscaler reaction speed to sudden load changes.

export const options = {
  stages: [
    { duration: "1m", target: 20 },
    { duration: "30s", target: 120 },
    { duration: "1m", target: 120 },
    { duration: "30s", target: 20 },
    { duration: "1m", target: 20 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.1);
}
