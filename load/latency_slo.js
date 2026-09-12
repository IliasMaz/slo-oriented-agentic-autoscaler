import http from "k6/http";
import { sleep } from "k6";

// Latency-awareness profile:
// Sustained application latency pressure with little CPU work. This separates
// an SLO-aware controller from a CPU-only HPA signal.
export const options = {
  stages: [
    { duration: "45s", target: 30 },
    { duration: "30s", target: 240 },
    { duration: "2m", target: 240 },
    { duration: "45s", target: 30 },
    { duration: "45s", target: 30 },
  ],
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.05);
}
