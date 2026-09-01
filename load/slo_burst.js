import http from "k6/http";
import { sleep } from "k6";

// SLO burst profile:
// Gives the controller time to establish a baseline, then creates a sustained
// application-level overload where proactive RPS/SLO-based scaling can differ
// from CPU-only HPA behavior.
export const options = {
  stages: [
    { duration: "45s", target: 30 },
    { duration: "30s", target: 180 },
    { duration: "90s", target: 180 },
    { duration: "30s", target: 40 },
    { duration: "45s", target: 40 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.1);
}
