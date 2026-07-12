import http from "k6/http";
import { sleep } from "k6";

// Burst load profile:
// Starts low, spikes to high traffic, then drops back down.
// Useful for testing autoscaler reaction speed to sudden load changes.

export const options = {
  stages: [
    { duration: "1m", target: 10 },
    { duration: "30s", target: 60 },
    { duration: "1m", target: 60 },
    { duration: "30s", target: 10 },
    { duration: "1m", target: 10 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.1);
}
