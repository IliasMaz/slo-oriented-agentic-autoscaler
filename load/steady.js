import http from "k6/http";
import { sleep } from "k6";

// Steady load profile:
// Keeps traffic relatively constant for 5 minutes with 15 virtual users.
// Useful as a baseline to observe normal autoscaler behavior.

export const options = {
  vus: 15,
  duration: "5m",
};

export default function () {
  http.get("http://localhost:8000/");
  sleep(0.2);
}
