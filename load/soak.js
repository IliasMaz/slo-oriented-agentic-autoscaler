import http from "k6/http";
import { sleep } from "k6";

// Soak profile:
// Keeps a moderate, long-running steady load.
// Useful for observing stability, cooldown behavior, and sustained SLO tracking.

export const options = {
  vus: 20,
  duration: "10m",
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.2);
}
